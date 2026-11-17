import math
from krita import DockWidget, Krita

try:
    from PyQt6.QtCore import Qt, QPointF, QRectF, QEvent, QCoreApplication
    from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QTransform,
                             QPolygonF, QRegion, QMouseEvent, QTabletEvent)
    from PyQt6.QtWidgets import (QWidget, QMdiArea, QVBoxLayout, QHBoxLayout,
                                 QPushButton, QLabel, QCheckBox, QSpinBox)
    PY_VER = 6
    _E = QEvent.Type
    ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
    HINT_ANTIALIAS = QPainter.RenderHint.Antialiasing
except ImportError:
    from PyQt5.QtCore import Qt, QPointF, QRectF, QEvent, QCoreApplication
    from PyQt5.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QTransform,
                             QPolygonF, QRegion, QMouseEvent, QTabletEvent)
    from PyQt5.QtWidgets import (QWidget, QMdiArea, QVBoxLayout, QHBoxLayout,
                                 QPushButton, QLabel, QCheckBox, QSpinBox)
    PY_VER = 5
    _E = QEvent
    ALIGN_CENTER = Qt.AlignCenter
    HINT_ANTIALIAS = QPainter.Antialiasing

_LEFT = getattr(Qt, "MouseButton", Qt).LeftButton

_PRESS = (_E.TabletPress, _E.MouseButtonPress)
_MOVE = (_E.TabletMove, _E.MouseMove)
_RELEASE = (_E.TabletRelease, _E.MouseButtonRelease)
_TABLET = (_E.TabletPress, _E.TabletMove, _E.TabletRelease)
_MOUSE = (_E.MouseButtonPress, _E.MouseMove, _E.MouseButtonRelease)
_POINTER = _PRESS + _MOVE + _RELEASE

DEBUG = False  # True: imprime no console o nome da classe do widget que recebe o clique


class RulerOverlayWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

        self.ruler_center = QPointF(400, 300)
        self.ruler_angle = 0.0
        self.ruler_length = 600.0
        self.ruler_thick = 50.0
        self.is_dragging = False
        self.drag_offset = QPointF()

    # ---------- geometria / máscara ----------
    def _transform(self):
        t = QTransform()
        t.translate(self.ruler_center.x(), self.ruler_center.y())
        t.rotate(self.ruler_angle)
        return t

    def _ruler_polygon(self):
        rect = QRectF(-self.ruler_length / 2, -self.ruler_thick / 2,
                      self.ruler_length, self.ruler_thick)
        return self._transform().map(QPolygonF(rect))

    def edge_points(self):
        """Extremidades da borda amarela (borda de apoio), em coordenadas do viewport."""
        t = self._transform()
        a = t.map(QPointF(-self.ruler_length / 2, -self.ruler_thick / 2))
        b = t.map(QPointF(self.ruler_length / 2, -self.ruler_thick / 2))
        return a, b

    def update_mask(self):
        """Só a área da régua recebe cliques; o resto passa para o canvas."""
        self.setMask(QRegion(self._ruler_polygon().toPolygon()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_mask()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_mask()

    # ---------- desenho ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(HINT_ANTIALIAS)

        painter.save()
        painter.translate(self.ruler_center)
        painter.rotate(self.ruler_angle)

        rect = QRectF(-self.ruler_length / 2, -self.ruler_thick / 2,
                      self.ruler_length, self.ruler_thick)
        painter.setBrush(QBrush(QColor(40, 140, 220, 80)))
        painter.setPen(QPen(QColor(120, 210, 255, 230), 2))
        painter.drawRoundedRect(rect, 4, 4)

        # Borda de apoio (é ela que guia o traço)
        painter.setPen(QPen(QColor(255, 220, 80, 250), 3))
        painter.drawLine(QPointF(-self.ruler_length / 2, -self.ruler_thick / 2),
                         QPointF(self.ruler_length / 2, -self.ruler_thick / 2))

        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.setFont(QFont("Sans", 8))
        painter.drawText(QRectF(-120, -10, 240, 20), ALIGN_CENTER,
                         "Régua: {:.1f}° (Arraste / Scroll)".format(self.ruler_angle))

        painter.restore()
        painter.end()

    # ---------- interação (mover / girar a régua) ----------
    def mousePressEvent(self, event):
        pos = event.position() if PY_VER == 6 else event.pos()
        self.is_dragging = True
        self.drag_offset = QPointF(pos) - self.ruler_center
        event.accept()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            pos = event.position() if PY_VER == 6 else event.pos()
            self.ruler_center = QPointF(pos) - self.drag_offset
            self.update_mask()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.is_dragging = False
        event.accept()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() / 120.0
        self.ruler_angle = (self.ruler_angle + delta * 5.0) % 360.0
        self.update_mask()
        self.update()
        event.accept()


class PhysicalRulerDocker(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Régua Física")
        self.ruler = None
        self.mdi_area = None

        self.lock_enabled = True
        self.snap_dist = 40
        self._filter_on = False
        self._sending = False
        self._locked = False

        container = QWidget(self)
        layout = QVBoxLayout()

        self.info_label = QLabel("Painel da Régua Física", container)
        layout.addWidget(self.info_label)

        self.btn_toggle = QPushButton("Mostrar / Ocultar Régua", container)
        self.btn_toggle.clicked.connect(self.toggle_ruler)
        layout.addWidget(self.btn_toggle)

        layout_rot = QHBoxLayout()
        btn_0 = QPushButton("0°", container)
        btn_0.clicked.connect(lambda: self.set_angle(0.0))
        btn_90 = QPushButton("90°", container)
        btn_90.clicked.connect(lambda: self.set_angle(90.0))
        layout_rot.addWidget(btn_0)
        layout_rot.addWidget(btn_90)
        layout.addLayout(layout_rot)

        # Trava do traço na régua
        self.chk_lock = QCheckBox("Travar traço na borda amarela", container)
        self.chk_lock.setChecked(True)
        self.chk_lock.toggled.connect(self._on_lock_toggled)
        layout.addWidget(self.chk_lock)

        layout_snap = QHBoxLayout()
        layout_snap.addWidget(QLabel("Captura (px):", container))
        self.spin_snap = QSpinBox(container)
        self.spin_snap.setRange(5, 300)
        self.spin_snap.setValue(self.snap_dist)
        self.spin_snap.valueChanged.connect(self._on_snap_changed)
        layout_snap.addWidget(self.spin_snap)
        layout.addLayout(layout_snap)

        layout.addStretch(1)
        container.setLayout(layout)
        self.setWidget(container)

    # Método obrigatório da classe DockWidget do Krita
    def canvasChanged(self, canvas):
        pass

    # ---------- configuração ----------
    def _on_lock_toggled(self, checked):
        self.lock_enabled = checked
        self._update_filter()

    def _on_snap_changed(self, value):
        self.snap_dist = value

    def _update_filter(self):
        """O filtro global só fica ativo quando a régua está visível e a trava ligada."""
        app = QCoreApplication.instance()
        want = bool(self.ruler and self.ruler.isVisible() and self.lock_enabled)
        if want and not self._filter_on:
            app.installEventFilter(self)
            self._filter_on = True
        elif not want and self._filter_on:
            app.removeEventFilter(self)
            self._filter_on = False
            self._locked = False

    # ---------- overlay ----------
    def _ensure_ruler(self):
        app = Krita.instance()
        window = app.activeWindow()
        if not window:
            return None
        qwin = window.qwindow()
        if not qwin:
            return None
        mdi = qwin.findChild(QMdiArea)
        if not mdi:
            return None

        if self.ruler is None or self.mdi_area is not mdi:
            if self.mdi_area is not None:
                try:
                    self.mdi_area.viewport().removeEventFilter(self)
                except RuntimeError:
                    pass
            self.mdi_area = mdi
            self.ruler = RulerOverlayWidget(mdi.viewport())
            self.ruler.setGeometry(mdi.viewport().rect())
            mdi.viewport().installEventFilter(self)

        return self.ruler

    def toggle_ruler(self):
        ruler = self._ensure_ruler()
        if not ruler:
            return
        if ruler.isVisible():
            ruler.hide()
            self.info_label.setText("Status: Oculta")
        else:
            ruler.setGeometry(self.mdi_area.viewport().rect())
            ruler.show()
            ruler.raise_()
            self.info_label.setText("Status: Visível na Tela")
        self._update_filter()

    def set_angle(self, angle):
        if self.ruler and self.ruler.isVisible():
            self.ruler.ruler_angle = angle
            self.ruler.update_mask()
            self.ruler.update()
            self.info_label.setText("Ângulo ajustado para {}°".format(angle))

    # ---------- trava do traço ----------
    @staticmethod
    def _positions(event):
        """(posição local, posição global) como QPointF, em Qt5 ou Qt6."""
        if PY_VER == 6:
            return event.position(), event.globalPosition()
        if event.type() in _TABLET:
            return event.posF(), event.globalPosF()
        return event.localPos(), event.screenPos()

    @staticmethod
    def _project(p, a, b):
        """Projeta o ponto p no segmento a-b (limitado às extremidades da régua)."""
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length2 = dx * dx + dy * dy
        t = 0.0
        if length2 > 0:
            t = ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length2
            t = max(0.0, min(1.0, t))
        return QPointF(a.x() + t * dx, a.y() + t * dy)

    def _is_canvas(self, obj):
        if not isinstance(obj, QWidget) or obj is self.ruler:
            return False
        if self.mdi_area is None or not self.mdi_area.isAncestorOf(obj):
            return False
        name = obj.metaObject().className()
        return "canvas" in name.lower()

    def _clone_event(self, e, local, glob):
        t = e.type()
        try:
            if t in _MOUSE:
                return QMouseEvent(t, local, glob, e.button(), e.buttons(), e.modifiers())
            if PY_VER == 6:
                return QTabletEvent(t, e.pointingDevice(), local, glob,
                                    e.pressure(), e.xTilt(), e.yTilt(),
                                    e.tangentialPressure(), e.rotation(), e.z(),
                                    e.modifiers(), e.button(), e.buttons())
            return QTabletEvent(t, local, glob, e.device(), e.pointerType(),
                                e.pressure(), e.xTilt(), e.yTilt(),
                                e.tangentialPressure(), e.rotation(), e.z(),
                                e.modifiers(), e.uniqueId(), e.button(), e.buttons())
        except Exception as ex:
            print("[Régua Física] não consegui recriar o evento:", ex)
            self.lock_enabled = False
            self.chk_lock.setChecked(False)
            return None

    def _handle_pointer(self, obj, event):
        t = event.type()
        vp = self.mdi_area.viewport()
        local, glob = self._positions(event)
        vp_pt = QPointF(vp.mapFromGlobal(glob.toPoint()))
        a, b = self.ruler.edge_points()
        proj = self._project(vp_pt, a, b)

        if t in _PRESS:
            if t == _E.MouseButtonPress and event.button() != _LEFT:
                self._locked = False
                return False
            dist = math.hypot(proj.x() - vp_pt.x(), proj.y() - vp_pt.y())
            self._locked = dist <= self.snap_dist
            if DEBUG:
                print("[Régua Física] press em", obj.metaObject().className(),
                      "dist=%.1f travado=%s" % (dist, self._locked))

        if not self._locked:
            return False

        delta = proj - vp_pt
        new_event = self._clone_event(event, local + delta, glob + delta)
        if t in _RELEASE:
            self._locked = False
        if new_event is None:
            return False

        self._sending = True
        try:
            QCoreApplication.sendEvent(obj, new_event)
        finally:
            self._sending = False
        return True  # engole o evento original

    def eventFilter(self, obj, event):
        t = event.type()

        # Mantém o overlay do tamanho da área do canvas ao redimensionar
        if t == _E.Resize:
            if (self.mdi_area is not None and self.ruler is not None
                    and obj is self.mdi_area.viewport()):
                self.ruler.setGeometry(self.mdi_area.viewport().rect())
            return False

        if self._sending or t not in _POINTER:
            return False
        if not (self.lock_enabled and self.ruler and self.ruler.isVisible()):
            return False
        if not self._is_canvas(obj):
            return False

        return self._handle_pointer(obj, event)