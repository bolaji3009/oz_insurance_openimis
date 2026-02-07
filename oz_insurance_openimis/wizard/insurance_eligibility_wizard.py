from odoo import api, fields, models
import requests
import json


class InsuranceEligibilityWizard(models.TransientModel):
    _name = 'insurance.eligibility.wizard'
    _description = 'Insurance Eligibility Check Wizard'

    partner_id = fields.Many2one(
        'res.partner',
        string='Patient',
        required=True,
        help='Patient to check insurance eligibility for'
    )

    coverage_ref = fields.Char(
        string='Coverage Reference',
        required=True,
        help='Insurance coverage reference number'
    )

    insurer_id = fields.Many2one(
        'res.partner',
        string='Insurer',
        help='Insurance company'
    )

    care_setting = fields.Selection([
        ('opd', 'OPD'),
        ('ipd', 'IPD')
    ], string='Care Setting',
        help='Care setting type (OPD or IPD)'
    )

    eligibility_response = fields.Text(
        string='Eligibility Response',
        readonly=True,
        help='Raw FHIR CoverageEligibilityResponse'
    )

    eligibility_result = fields.Html(
        string='Eligibility Result',
        readonly=True,
        help='Formatted eligibility check result'
    )

    @api.model
    def _get_insurance_api_config(self):
        """Get insurance service API configuration from system parameters"""
        config = self.env['ir.config_parameter'].sudo()
        return {
            'url': config.get_param('oz_insurance_openimis.insurance_svc_url', 'https://api.openimis.org/fhir'),
            'token': config.get_param('oz_insurance_openimis.insurance_svc_auth_token', '')
        }

    def _prepare_fhir_eligibility_request(self):
        """Prepare FHIR CoverageEligibilityRequest structure"""
        request_data = {
            "resourceType": "CoverageEligibilityRequest",
            "status": "active",
            "priority": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/processpriority",
                        "code": "normal",
                        "display": "Normal"
                    }
                ]
            },
            "purpose": ["validation"],
            "patient": {
                "reference": f"Patient/{self.partner_id.ref}" if self.partner_id.ref else None
            },
            "servicedDate": fields.Date.today().isoformat(),
            "created": fields.Datetime.now().isoformat(),
            "insurer": {
                "reference": f"Organization/{self.insurer_id.ref}" if self.insurer_id and self.insurer_id.ref else None
            },
            "provider": {
                "reference": "Organization/" + str(self.env.company.id)
            },
            "insurance": [
                {
                    "focal": True,
                    "coverage": {
                        "reference": f"Coverage/{self.coverage_ref}"
                    }
                }
            ]
        }

        return request_data

    def action_check_eligibility(self):
        """Check insurance eligibility using openIMIS FHIR API"""
        config = self._get_insurance_api_config()
        
        for wizard in self:
            try:
                # Prepare and submit eligibility request
                request_data = wizard._prepare_fhir_eligibility_request()
                
                headers = {
                    'Content-Type': 'application/fhir+json',
                    'Authorization': f'Bearer {config["token"]}'
                } if config['token'] else {
                    'Content-Type': 'application/fhir+json'
                }
                
                response = requests.post(
                    f"{config['url']}/CoverageEligibilityRequest",
                    json=request_data,
                    headers=headers
                )
                
                if response.status_code == 201:
                    eligibility_response = response.json()
                    wizard.eligibility_response = json.dumps(eligibility_response, indent=2)
                    
                    # Search for CoverageEligibilityResponse
                    response_search = requests.get(
                        f"{config['url']}/CoverageEligibilityResponse?request={eligibility_response['id']}",
                        headers=headers
                    )
                    
                    if response_search.status_code == 200:
                        response_data = response_search.json()
                        if 'entry' in response_data and len(response_data['entry']) > 0:
                            eligibility_result = response_data['entry'][0]['resource']
                            wizard._parse_eligibility_response(eligibility_result)
                    else:
                        wizard.eligibility_result = "<p>No eligibility response received yet.</p>"
                        
                else:
                    raise Exception(f"Eligibility check failed: {response.text}")
                    
            except Exception as e:
                wizard.eligibility_result = f"<p style='color: red;'>Error: {str(e)}</p>"
                raise

    def _parse_eligibility_response(self, eligibility_result):
        """Parse and format FHIR CoverageEligibilityResponse"""
        html_result = []
        
        # Add coverage details
        if 'insurance' in eligibility_result:
            for insurance in eligibility_result['insurance']:
                if 'coverage' in insurance:
                    html_result.append(f"<h4>Coverage: {insurance['coverage']['display']}</h4>")
                
                if 'benefitPeriod' in insurance:
                    period = insurance['benefitPeriod']
                    period_text = f"{period['start']} to {period['end']}"
                    html_result.append(f"<p>Coverage Period: {period_text}</p>")
                
                # Add benefit details
                if 'item' in insurance:
                    for item in insurance['item']:
                        if 'productOrService' in item:
                            product = item['productOrService']
                            html_result.append(f"<h5>Service: {product['display']}</h5>")
                        
                        if 'benefit' in item:
                            for benefit in item['benefit']:
                                benefit_text = f"{benefit['type']['display']}: "
                                if 'allowed' in benefit:
                                    benefit_text += f"Allowed: {benefit['allowed']['value']}"
                                if 'used' in benefit:
                                    benefit_text += f", Used: {benefit['used']['value']}"
                                html_result.append(f"<p>{benefit_text}</p>")
        
        self.eligibility_result = ''.join(html_result)
