import sys
import random

from PySide6.QtWidgets import QApplication
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *


class Viewport(QOpenGLWidget):

    def __init__(self):
        super().__init__()

        self.points = [
            (
                random.uniform(-10, 10),
                random.uniform(-10, 10),
                random.uniform(-10, 10),
            )
            for _ in range(1000)
        ]

    def initializeGL(self):
        glClearColor(0.15, 0.15, 0.18, 1.0)

        glEnable(GL_DEPTH_TEST)

        glPointSize(6)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()

        gluPerspective(
            45,
            w / max(1, h),
            0.1,
            100,
        )

        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glLoadIdentity()

        # Move camera backwards
        glTranslatef(0, 0, -30)

        glBegin(GL_POINTS)

        glColor3f(1, 0, 0)

        quad = gluNewQuadric()

        for x, y, z in self.points:
            glPushMatrix()

            glTranslatef(x, y, z)
            gluSphere(quad, 0.1, 12, 12)

            glPopMatrix()

        glEnd()


app = QApplication(sys.argv)

w = Viewport()
w.resize(800, 600)
w.show()

app.exec()