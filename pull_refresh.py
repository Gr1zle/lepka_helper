"""Native refresh gesture and a portable scroll fallback, one scroll owner."""
import flet as ft
from flet.core.constrained_control import ConstrainedControl


class PullRefresh(ConstrainedControl):
    def __init__(self,content,onRefresh):
        super().__init__(expand=True)
        self.content=content
        self._add_event_handler('refresh',self._refresh)
        self.onRefresh=onRefresh
    def _get_control_name(self):return 'lepka_refresh'
    def _get_children(self):
        self.content._set_attr_internal('n','content')
        return [self.content]
    def _refresh(self,event):
        try:self.onRefresh(event)
        finally:
            self._set_attr('refreshDone',event.data)
            self.update()


def refreshable(page,controls,onRefresh):
    from views.project_transfer import androidClient
    if androidClient(page):return PullRefresh(ft.Column(controls,spacing=12),onRefresh)
    return ft.ListView(controls=[ft.Column(controls,spacing=12)],expand=True,padding=16,build_controls_on_demand=False)
