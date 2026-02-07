from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_insurance_claim = fields.Boolean(
        string='Is Insurance Claim',
        default=False,
        tracking=True,
        help='Indicates if this sales order is an insurance claim'
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
        """Prepare FHIR Claim structure from sales order data"""
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
            "use": "preauthorization",
            "patient": {
                "reference": f"Patient/{self.partner_id.ref}" if self.partner_id.ref else None
            },
            "billablePeriod": {
                "start": self.date_order.date().isoformat(),
                "end": self.validity_date.isoformat() if self.validity_date else self.date_order.date().isoformat()
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
        for line in self.order_line:
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
                "quantity": line.product_uom_qty,
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
        """Submit sales order as insurance claim to openIMIS"""
        # This method would be implemented similarly to the invoice version
        # For preauthorization purposes
        config = self._get_insurance_api_config()
        
        for order in self:
            if not order.is_insurance_claim:
                order.is_insurance_claim = True
                
            # Prepare and submit FHIR Claim for preauthorization
            claim_data = order._prepare_fhir_claim()
            
            try:
                import requests
                import json
                
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
                    order.openimis_claim_id = claim_response.get('id')
                    order.claim_status = 'submitted'
                    order.message_post(body='Insurance claim preauthorization submitted to openIMIS')
                else:
                    raise Exception(f"Failed to submit claim: {response.text}")
                    
            except Exception as e:
                order.message_post(body=f"Error submitting insurance claim: {str(e)}")
                raise
