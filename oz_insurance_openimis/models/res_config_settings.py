from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    insurance_svc_url = fields.Char(
        string='Insurance Service URL',
        config_parameter='oz_insurance_openimis.insurance_svc_url',
        default='https://api.openimis.org/fhir',
        help='Base URL for the openIMIS FHIR API endpoint'
    )
    
    insurance_svc_auth_token = fields.Char(
        string='Auth Token',
        config_parameter='oz_insurance_openimis.insurance_svc_auth_token',
        help='Authentication token for accessing the openIMIS FHIR API'
    )
    
    insurance_pricelist_parity_enabled = fields.Boolean(
        string='Enable Pricelist Parity Check',
        config_parameter='oz_insurance_openimis.insurance_pricelist_parity_enabled',
        default=True,
        help='Enable nightly pricelist parity check with openIMIS'
    )
    
    insurance_parity_check_time = fields.Integer(
        string='Parity Check Time (Hour)',
        config_parameter='oz_insurance_openimis.insurance_parity_check_time',
        default=2,
        help='Hour of the day to run the pricelist parity check (0-23)'
    )
