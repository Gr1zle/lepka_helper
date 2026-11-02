"""Shared, theme-aware presentation. No application data or navigation side effects."""
import flet as ft

PRIMARY_COLOR = '#355F4B'
SECONDARY_COLOR = '#9A4F36'
ICON = 'icon.png'


def makeTheme(dark=False):
    surface = '#171D19' if dark else '#F6F5EF'
    onSurface = '#E6EAE3' if dark else '#202C25'
    primary = '#AFD3BA' if dark else PRIMARY_COLOR
    scheme = ft.ColorScheme(primary=primary, on_primary='#193827' if dark else '#FFFFFF',
        secondary='#F0B89E' if dark else SECONDARY_COLOR,
        surface=surface, on_surface=onSurface,
        surface_container_low='#202822' if dark else '#FFFFFF',
        surface_container='#273129' if dark else '#EDEFE6',
        surface_variant='#202822' if dark else '#FFFFFF',
        surface_container_high='#303C32' if dark else '#E6EADD',
        on_surface_variant='#BCC7BC' if dark else '#58665B',
        outline='#849184' if dark else '#7D8A7C', outline_variant='#404E42' if dark else '#D4DBCF',
        primary_container='#314F3C' if dark else '#DCEAD8',
        on_primary_container='#D5EAD8' if dark else '#244831')
    shape=ft.RoundedRectangleBorder(radius=14)
    return ft.Theme(use_material3=True, color_scheme_seed=PRIMARY_COLOR, color_scheme=scheme,
        visual_density=ft.VisualDensity.STANDARD,
        scaffold_bgcolor=surface,
        text_theme=ft.TextTheme(
            body_large=ft.TextStyle(size=16,color=onSurface),
            body_medium=ft.TextStyle(size=14,color=onSurface),
            body_small=ft.TextStyle(size=12,color=onSurface),
            title_large=ft.TextStyle(size=22,weight=ft.FontWeight.W_600,color=onSurface),
            title_medium=ft.TextStyle(size=16,weight=ft.FontWeight.W_600,color=onSurface),
            title_small=ft.TextStyle(size=14,weight=ft.FontWeight.W_600,color=onSurface),
            headline_large=ft.TextStyle(size=32,color=onSurface),
            headline_medium=ft.TextStyle(size=28,color=onSurface),
            headline_small=ft.TextStyle(size=24,color=onSurface),
            display_large=ft.TextStyle(size=48,color=onSurface),
            display_medium=ft.TextStyle(size=40,color=onSurface),
            display_small=ft.TextStyle(size=36,color=onSurface),
            label_large=ft.TextStyle(size=14,weight=ft.FontWeight.W_600,color=onSurface),
            label_medium=ft.TextStyle(size=12,color=onSurface),
            label_small=ft.TextStyle(size=11,color=onSurface)),
        dialog_theme=ft.DialogTheme(bgcolor='#202822' if dark else '#FFFFFF',elevation=0,shape=ft.RoundedRectangleBorder(radius=20),
            title_text_style=ft.TextStyle(size=22,color=onSurface,weight=ft.FontWeight.W_600),
            content_text_style=ft.TextStyle(size=14,color=onSurface)),
        card_theme=ft.CardTheme(color='#202822' if dark else '#FFFFFF',elevation=0,shape=shape,margin=0),
        elevated_button_theme=ft.ElevatedButtonTheme(elevation=0,shape=shape,
            padding=ft.padding.symmetric(horizontal=18,vertical=12),minimum_size=ft.Size(48,48)),
        outlined_button_theme=ft.OutlinedButtonTheme(shape=shape,
            padding=ft.padding.symmetric(horizontal=16,vertical=12),minimum_size=ft.Size(48,48)),
        text_button_theme=ft.TextButtonTheme(shape=shape,minimum_size=ft.Size(48,44)),
        navigation_bar_theme=ft.NavigationBarTheme(elevation=0,height=72,
            bgcolor='#202822' if dark else '#FFFFFF',indicator_color='#314F3C' if dark else '#DCEAD8',
            label_padding=ft.padding.all(0),label_text_style=ft.TextStyle(size=12,color=onSurface)),
        appbar_theme=ft.AppBarTheme(bgcolor=surface,elevation=0,
            center_title=False,title_text_style=ft.TextStyle(size=20,weight=ft.FontWeight.W_600,color=onSurface)))


def disclosure(title, controls, icon=None):
    return ft.Card(content=ft.ExpansionTile(title=ft.Text(title,weight=ft.FontWeight.W_600),
        leading=ft.Icon(icon) if icon else None,
        controls=[ft.Container(padding=ft.padding.only(left=14,right=14,top=10,bottom=14),
            content=ft.Column(controls=controls,spacing=12))],maintain_state=True))


def workspace(page, title, groups):
    """Switch tasks without rebuilding fields, images, callbacks or recipe state."""
    panels=[ft.Column(controls=controls,spacing=12,visible=i==0) for i,(_,controls) in enumerate(groups)]
    buttons=[]
    def select(index):
        for i,panel in enumerate(panels):
            panel.visible=i==index
            buttons[i].style=ft.ButtonStyle(bgcolor=ft.Colors.PRIMARY_CONTAINER if i==index else ft.Colors.SURFACE_CONTAINER_HIGHEST,
                color=ft.Colors.ON_PRIMARY_CONTAINER if i==index else ft.Colors.ON_SURFACE_VARIANT,
                shape=ft.RoundedRectangleBorder(radius=12))
        page.update()
    for i,(label,_) in enumerate(groups):
        buttons.append(ft.TextButton(label,on_click=lambda e,index=i:select(index),
            style=ft.ButtonStyle(bgcolor=ft.Colors.PRIMARY_CONTAINER if i==0 else ft.Colors.SURFACE_CONTAINER_HIGHEST,
                color=ft.Colors.ON_PRIMARY_CONTAINER if i==0 else ft.Colors.ON_SURFACE_VARIANT,
                shape=ft.RoundedRectangleBorder(radius=12))))
    view=ft.ListView(expand=True,build_controls_on_demand=False,padding=16,spacing=14,
        controls=[ft.Text(title,size=24,weight=ft.FontWeight.W_600),ft.Row(buttons,wrap=True,spacing=6,run_spacing=6),*panels])
    view.select_workspace=select
    return view


def polish(root):
    """Presentation defaults also cover secondary routes and dynamically made cards.

    Swatch / photo / model colours are deliberately left intact.
    """
    def visit(control):
        if isinstance(control,ft.Text) and control.color in (ft.Colors.GREY_600,ft.Colors.GREY_700,ft.Colors.BLACK87):
            control.color=ft.Colors.ON_SURFACE_VARIANT
        if isinstance(control,ft.Card):control.elevation=0
        if isinstance(control,(ft.TextField,ft.Dropdown)):
            control.border_radius=12
            control.content_padding=ft.padding.symmetric(horizontal=14,vertical=13)
            control.border_color=ft.Colors.OUTLINE_VARIANT
            control.focused_border_color=ft.Colors.PRIMARY
        if isinstance(control,ft.Row) and control.wrap:control.run_spacing=max(control.run_spacing or 0,6)
        for child in control._get_children():visit(child)
    visit(root)
    return root


def presentView(page, view):
    polish(view)
    if len(view.controls)==1 and isinstance(view.controls[0],ft.ListView) and view.controls[0].width is None:
        inner=ft.Container(width=min(1040,page.width or 390),expand=True,content=view.controls[0])
        inner._design_bound=True
        view.controls=[ft.Container(expand=True,alignment=ft.alignment.top_center,content=inner)]
    return view


def resizeLayouts(page):
    def visit(control):
        if getattr(control,'_design_bound',False):control.width=min(1040,page.width or 390)
        for child in control._get_children():visit(child)
    for view in page.views:visit(view)


def relativeLuminance(value):
    channels=[int(value.lstrip('#')[i:i+2],16)/255 for i in (0,2,4)]
    channels=[c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4 for c in channels]
    return sum(c*w for c,w in zip(channels,(0.2126,0.7152,0.0722)))


def swatchTextColor(value):
    luminance=relativeLuminance(value)
    return ft.Colors.BLACK if (luminance+0.05)/0.05 >= 1.05/(luminance+0.05) else ft.Colors.WHITE
