from odoo import models, api
from odoo.exceptions import ValidationError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def _post_inventory(self, cancel_backorder=False):
        for order in self:
            for move in order.move_raw_ids.filtered(
                lambda m: m.state not in ('done', 'cancel') and m.product_uom_qty > 0
            ):
                if move.product_id.qty_available < move.product_uom_qty:
                    raise ValidationError(
                        'No hay suficiente stock de "%s" '
                        'para producir. Necesario: %.2f, '
                        'Disponible: %.2f' % (
                            move.product_id.display_name,
                            move.product_uom_qty,
                            move.product_id.qty_available,
                        )
                    )
        return super()._post_inventory(cancel_backorder=cancel_backorder)
