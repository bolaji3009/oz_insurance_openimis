from odoo import api, fields, models
import requests
import json


class PricelistParity(models.Model):
    _name = 'pricelist.parity'
    _description = 'Pricelist Parity Check'
    _rec_name = 'pricelist_id'

    pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Pricelist',
        required=True,
        help='Pricelist to check for parity with openIMIS'
    )

    last_check_date = fields.Datetime(
        string='Last Check Date',
        help='Date and time of last parity check'
    )

    parity_status = fields.Selection([
        ('in_sync', 'In Sync'),
        ('out_of_sync', 'Out of Sync'),
        ('error', 'Error')
    ], string='Parity Status',
        help='Current parity status with openIMIS'
    )

    discrepancy_count = fields.Integer(
        string='Discrepancy Count',
        help='Number of price discrepancies found'
    )

    error_message = fields.Text(
        string='Error Message',
        help='Error message if check failed'
    )

    @api.model
    def _get_insurance_api_config(self):
        """Get insurance service API configuration from system parameters"""
        config = self.env['ir.config_parameter'].sudo()
        return {
            'url': config.get_param('oz_insurance_openimis.insurance_svc_url', 'https://api.openimis.org/fhir'),
            'token': config.get_param('oz_insurance_openimis.insurance_svc_auth_token', '')
        }

    def _get_openimis_prices(self, pricelist):
        """Get prices from openIMIS for comparison"""
        config = self._get_insurance_api_config()
        
        try:
            headers = {
                'Authorization': f'Bearer {config["token"]}'
            } if config['token'] else {}
            
            # Fetch pricing information from openIMIS
            # This is a placeholder - actual endpoint will depend on openIMIS implementation
            response = requests.get(
                f"{config['url']}/ValueSet/openimis-prices",
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Failed to fetch prices: {response.text}")
                
        except Exception as e:
            raise Exception(f"Error fetching prices from openIMIS: {str(e)}")

    def check_pricelist_parity(self):
        """Check pricelist parity with openIMIS"""
        for record in self:
            try:
                # Get prices from both systems
                openimis_prices = self._get_openimis_prices(record.pricelist_id)
                odoo_prices = self._get_odoo_prices(record.pricelist_id)
                
                # Compare prices and find discrepancies
                discrepancies = self._compare_prices(openimis_prices, odoo_prices)
                
                # Update parity status
                record.discrepancy_count = len(discrepancies)
                record.last_check_date = fields.Datetime.now()
                
                if discrepancies:
                    record.parity_status = 'out_of_sync'
                    record.error_message = str(discrepancies)
                else:
                    record.parity_status = 'in_sync'
                    record.error_message = ''
                    
                record._log_parity_result(discrepancies)
                
            except Exception as e:
                record.parity_status = 'error'
                record.error_message = str(e)
                record.last_check_date = fields.Datetime.now()
                record.discrepancy_count = 0

    def _get_odoo_prices(self, pricelist):
        """Get prices from Odoo pricelist"""
        prices = []
        
        # Get all active products with prices in this pricelist
        product_prices = self.env['product.pricelist.item'].search([
            ('pricelist_id', '=', pricelist.id),
            ('applied_on', 'in', ['0_product_variant', '1_product'])
        ])
        
        for price_item in product_prices:
            product = price_item.product_id or price_item.product_tmpl_id
            prices.append({
                'product_code': product.default_code or str(product.id),
                'product_name': product.name,
                'price': price_item.fixed_price,
                'currency': pricelist.currency_id.name
            })
            
        return prices

    def _compare_prices(self, openimis_prices, odoo_prices):
        """Compare prices from openIMIS and Odoo"""
        discrepancies = []
        
        # Create dictionaries for easy comparison
        odoo_price_dict = {price['product_code']: price for price in odoo_prices}
        
        # This is a placeholder - actual openIMIS price structure may vary
        for item in openimis_prices.get('expansion', {}).get('contains', []):
            product_code = item.get('code')
            if product_code in odoo_price_dict:
                odoo_price = odoo_price_dict[product_code]
                openimis_price = item.get('valueQuantity', {}).get('value')
                
                if abs(odoo_price['price'] - openimis_price) > 0.01:  # Allow small rounding differences
                    discrepancies.append({
                        'product_code': product_code,
                        'product_name': odoo_price['product_name'],
                        'odoo_price': odoo_price['price'],
                        'openimis_price': openimis_price,
                        'difference': abs(odoo_price['price'] - openimis_price)
                    })
        
        return discrepancies

    def _log_parity_result(self, discrepancies):
        """Log parity check results"""
        for record in self:
            body = f"Pricelist parity check for {record.pricelist_id.name} completed"
            if discrepancies:
                body += f". Found {len(discrepancies)} price discrepancies:"
                for disc in discrepancies:
                    body += f"\n- {disc['product_name']} (Code: {disc['product_code']}): " \
                          f"Odoo: {disc['odoo_price']}, openIMIS: {disc['openimis_price']}"
            else:
                body += ". All prices are in sync with openIMIS."
                
            record.message_post(body=body)

    @api.model
    def run_nightly_pricelist_parity_check(self):
        """Run nightly pricelist parity check"""
        config = self.env['ir.config_parameter'].sudo()
        enabled = config.get_param('oz_insurance_openimis.insurance_pricelist_parity_enabled', 'True')
        
        if enabled == 'True':
            # Get all pricelists configured for insurance
            insurance_pricelists = self.env['product.pricelist'].search([])  # This should be filtered
            
            for pricelist in insurance_pricelists:
                # Check if we already have a parity record for this pricelist
                parity_record = self.search([('pricelist_id', '=', pricelist.id)], limit=1)
                
                if not parity_record:
                    parity_record = self.create({'pricelist_id': pricelist.id})
                    
                parity_record.check_pricelist_parity()
