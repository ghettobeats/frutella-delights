from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    min_stock = fields.Float(string='Stock Mínimo', digits=(16, 2), default=0.0)
    low_stock = fields.Boolean(
        string='Stock Bajo',
        compute='_compute_low_stock',
        store=True,
    )

    @api.depends('qty_available', 'min_stock')
    def _compute_low_stock(self):
        for rec in self:
            rec.low_stock = rec.qty_available <= rec.min_stock

    def action_send_low_stock_alert(self):
        products = self.search([('low_stock', '=', True)])
        if not products:
            return

        template = self.env.ref('frutella.mail_template_low_stock', raise_if_not_found=False)
        if not template:
            return

        recipients = self._get_alert_recipients()
        if not recipients:
            return

        emails = ','.join(filter(None, recipients.mapped('email')))
        if not emails:
            return

        template.with_context(
            low_stock_product_ids=products.ids,
        ).send_mail(
            products[0].id,
            email_values={'email_to': emails},
            force_send=True,
        )

    def _get_alert_recipients(self):
        group = self.env.ref('frutella.group_frutella_fabrica', raise_if_not_found=False)
        if group and group.users:
            return group.users
        return self.env.ref('base.user_admin')
