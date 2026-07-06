from odoo import models, fields, api
from odoo.exceptions import ValidationError


class MsSale(models.Model):
    _name = 'ms.sale'
    _description = 'Venta'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, date desc, id desc'

    sequence = fields.Integer(string='Secuencia', default=10)
    name = fields.Char(string='Referencia', required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ms.sale') or 'Nueva')
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one('res.currency',
                                  default=lambda self: self.env.company.currency_id)
    sale_line_ids = fields.One2many('ms.sale.line', 'sale_id', string='Productos')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Realizado'),
    ], string='Estado', default='draft')

    total = fields.Float(string='Total', compute='_compute_total', store=True)
    total_cost = fields.Float(string='Costo Total', compute='_compute_total', store=True)
    profit = fields.Float(string='Ganancia/Pérdida', compute='_compute_total', store=True)

    @api.depends('sale_line_ids.subtotal', 'sale_line_ids.cost')
    def _compute_total(self):
        for rec in self:
            rec.total = sum(rec.sale_line_ids.mapped('subtotal'))
            rec.total_cost = sum(rec.sale_line_ids.mapped('cost'))
            rec.profit = rec.total - rec.total_cost

    def action_confirm(self):
        if self.filtered(lambda r: r.state == 'done'):
            raise ValidationError('Una o más ventas ya fueron realizadas.')

        for rec in self:
            picking = self.env['stock.picking'].create({
                'name': rec.name,
                'location_id': self.env.ref('stock.stock_location_stock').id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
                'picking_type_id': self.env.ref('stock.picking_type_out').id,
            })

            for line in rec.sale_line_ids:
                if line.product_id.sudo().qty_available < line.quantity:
                    raise ValidationError(
                        f'Stock insuficiente de "{line.product_id.name}". '
                        f'Disponible: {line.product_id.sudo().qty_available}.'
                    )

                move = self.env['stock.move'].create({
                    'name': rec.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': self.env.ref('stock.stock_location_stock').id,
                    'location_dest_id': self.env.ref('stock.stock_location_customers').id,
                    'picking_id': picking.id,
                })
                move._action_confirm()
                move._action_assign()
                move.quantity = line.quantity
                move._action_done()

            rec.state = 'done'

            if rec.profit < 0:
                template = self.env.ref('frutella.mail_template_sale_loss', raise_if_not_found=False)
                if template:
                    admin = self.env.ref('base.user_admin')
                    template.send_mail(
                        rec.id,
                        email_values={'email_to': admin.email},
                        force_send=True,
                    )

    def unlink(self):
        if self.filtered(lambda r: r.state == 'done'):
            raise ValidationError('No se puede eliminar una venta confirmada.')
        return super().unlink()


class MsSaleLine(models.Model):
    _name = 'ms.sale.line'
    _description = 'Línea de Venta'

    sale_id = fields.Many2one('ms.sale', string='Venta', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    quantity = fields.Float(string='Cantidad', digits=(16, 2), required=True)
    price = fields.Float(string='Precio de Venta', digits=(16, 2),
                         compute='_compute_price_cost', store=True)
    cost_unit = fields.Float(string='Costo Unitario', digits=(16, 2),
                             compute='_compute_price_cost', store=True)
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)
    cost = fields.Float(string='Costo Total', compute='_compute_subtotal', store=True)

    @api.depends('product_id')
    def _compute_price_cost(self):
        for rec in self:
            rec.price = rec.product_id.list_price if rec.product_id else 0.0
            if not rec.product_id:
                rec.cost_unit = 0.0
                continue
            bom = self.env['mrp.bom'].search([
                ('product_tmpl_id', '=', rec.product_id.product_tmpl_id.id)
            ], limit=1)
            if not bom or not bom.product_qty:
                rec.cost_unit = 0.0
                continue
            costo_total = sum(line.product_id.standard_price * line.product_qty
                             for line in bom.bom_line_ids)
            rec.cost_unit = costo_total / bom.product_qty

    @api.depends('quantity', 'price', 'cost_unit')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.quantity * rec.price
            rec.cost = rec.quantity * rec.cost_unit
