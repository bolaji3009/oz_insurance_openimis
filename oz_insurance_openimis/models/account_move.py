from odoo import api, fields, models
import requests
import json


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_insurance_claim = fields.Boolean(
        string='Is Insurance Claim',
        default=False,
        tracking=True,
        help='Indicates if this invoice is an insurance claim'
    )

    care_setting = fields.Selection([
        ('opd', 'OPD'),
        ('ipd', 'IPD')
    ], string='Care Setting', tracking=True,
        help='Care setting type (OPD or IPD)')

    coverage_ref = fields.Char(
        string='Coverage Reference',
        tracking=True,
        help='Reference to the insurance coverage'
    )

    insurer = fields.Many2one(
        'res.partner',
        string='Insurer',
        tracking=True,
        help='Insurance company'
    )

    openimis_claim_id = fields.Char(
        string='openIMIS Claim ID',
        tracking=True,
        help='Claim ID from openIMIS system'
    )

    claim_status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
        ('cancelled', 'Cancelled')
    ], string='Claim Status',
        default='draft',
        tracking=True,
        help='Current status of the insurance claim'
    )

    approved_total = fields.Monetary(
        string='Approved Amount',
        currency_field='currency_id',
        tracking=True,
        help='Total amount approved by the insurer'
    )

    denied_total = fields.Monetary(
        string='Denied Amount',
        currency_field='currency_id',
        tracking=True,
        help='Total amount denied by the insurer'
    )

    @api.model
    def _get_insurance_api_config(self):
        """Get insurance service API configuration from system parameters"""
        config = self.env['ir.config_parameter'].sudo()
        return {
            'url': config.get_param('oz_insurance_openimis.insurance_svc_url', 'https://api.openimis.org/fhir'),
            'token': config.get_param('oz_insurance_openimis.insurance_svc_auth_token', '')
        }

    def _prepare_fhir_claim(self):
        """Prepare FHIR Claim structure from invoice data"""
        claim_data = {
            "resourceType": "Claim",
            "type": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                        "code": self.care_setting,
                        "display": self.care_setting.upper()
                    }
                ]
            },
            "use": "claim",
            "patient": {
                "reference": f"Patient/{self.partner_id.ref}" if self.partner_id.ref else None
            },
            "billablePeriod": {
                "start": self.invoice_date.isoformat(),
                "end": self.invoice_date.isoformat()
            },
            "created": fields.Datetime.now().isoformat(),
            "insurer": {
                "reference": f"Organization/{self.insurer.ref}" if self.insurer and self.insurer.ref else None
            },
            "coverage": {
                "reference": f"Coverage/{self.coverage_ref}"
            },
            "item": []
        }

        # Add line items
        for line in self.invoice_line_ids:
            if line.display_type == 'line_section':
                continue
                
            item = {
                "sequence": line.sequence,
                "careTeamSequence": 1,
                "productOrService": {
                    "coding": [
                        {
                            "system": "http://openimis.org/codes/service",
                            "code": line.product_id.default_code or line.product_id.id,
                            "display": line.product_id.name
                        }
                    ]
                },
                "quantity": line.quantity,
                "unitPrice": {
                    "value": line.price_unit,
                    "currency": self.currency_id.name
                },
                "net": {
                    "value": line.price_subtotal,
                    "currency": self.currency_id.name
                }
            }
            
            claim_data["item"].append(item)

        return claim_data

    def action_submit_insurance_claim(self):
        """Submit invoice as insurance claim to openIMIS"""
        config = self._get_insurance_api_config()
        
        for invoice in self:
            if not invoice.is_insurance_claim:
                invoice.is_insurance_claim = True
                
            # Prepare and submit FHIR Claim
            claim_data = invoice._prepare_fhir_claim()
            
            try:
                headers = {
                    'Content-Type': 'application/fhir+json',
                    'Authorization': f'Bearer {config["token"]}'
                } if config['token'] else {
                    'Content-Type': 'application/fhir+json'
                }
                
                response = requests.post(
                    f"{config['url']}/Claim",
                    json=claim_data,
                    headers=headers
                )
                
                if response.status_code == 201:
                    claim_response = response.json()
                    invoice.openimis_claim_id = claim_response.get('id')
                    invoice.claim_status = 'submitted'
                    invoice.message_post(body='Insurance claim submitted to openIMIS')
                else:
                    raise Exception(f"Failed to submit claim: {response.text}")
                    
            except Exception as e:
                invoice.message_post(body=f"Error submitting insurance claim: {str(e)}")
                raise

    def action_refresh_claim_status(self):
        """Refresh insurance claim status from openIMIS"""
        config = self._get_insurance_api_config()
        
        for invoice in self:
            if not invoice.openimis_claim_id:
                continue
                
            try:
                headers = {
                    'Authorization': f'Bearer {config["token"]}'
                } if config['token'] else {}
                
                # Get Claim and ClaimResponse from openIMIS
                claim_response = requests.get(
                    f"{config['url']}/Claim/{invoice.openimis_claim_id}",
                    headers=headers
                )
                
                if claim_response.status_code == 200:
                    claim_data = claim_response.json()
                    # Update claim status based on FHIR Claim status
                    status_map = {
                        'active': 'submitted',
                        'completed': 'approved',
                        'cancelled': 'cancelled'
                    }
                    if 'status' in claim_data:
                        invoice.claim_status = status_map.get(claim_data['status'], 'draft')
                        
                    # Look for ClaimResponse
                    response_search = requests.get(
                        f"{config['url']}/ClaimResponse?claim={invoice.openimis_claim_id}",
                        headers=headers
                    )
                    
                    if response_search.status_code == 200:
                        response_data = response_search.json()
                        if 'entry' in response_data and len(response_data['entry']) > 0:
                            claim_response = response_data['entry'][0]['resource']
                            # Extract approved and denied amounts
                            if 'total' in claim_response:
                                invoice.approved_total = claim_response['total']['value']
                                invoice.denied_total = invoice.amount_total - invoice.approved_total
                                
                    invoice.message_post(body='Insurance claim status updated')
                    
            except Exception as e:
                invoice.message_post(body=f"Error refreshing claim status: {str(e)}")
                raise
