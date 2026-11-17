from krita import Krita, DockWidgetFactory, DockWidgetFactoryBase
from .docker import PhysicalRulerDocker

Krita.instance().addDockWidgetFactory(
    DockWidgetFactory(
        "physical_ruler_docker",
        DockWidgetFactoryBase.DockRight,
        PhysicalRulerDocker,
    )
)