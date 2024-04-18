# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'random_settings_weights_window.ui'
##
## Created by: Qt User Interface Compiler version 6.6.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QDialog, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget)
class Ui_RandomSettingsWeightsWindow(object):
    def setupUi(self, RandomSettingsWeightsWindow):
        if not RandomSettingsWeightsWindow.objectName():
            RandomSettingsWeightsWindow.setObjectName(u"RandomSettingsWeightsWindow")
        RandomSettingsWeightsWindow.resize(600, 800)
        self.vboxLayout = QVBoxLayout(RandomSettingsWeightsWindow)
        self.vboxLayout.setContentsMargins(0, 0, 0, 0)
        self.vboxLayout.setObjectName(u"vboxLayout")
        self.weightsText = QTextEdit(RandomSettingsWeightsWindow)
        self.weightsText.setObjectName(u"weightsText")
        self.weightsText.setReadOnly(True)
        self.weightsText.setGeometry(QRect(0, 0, 600, 800))

        self.vboxLayout.addWidget(self.weightsText)


        self.retranslateUi(RandomSettingsWeightsWindow)

        QMetaObject.connectSlotsByName(RandomSettingsWeightsWindow)
    # setupUi

    def retranslateUi(self, RandomSettingsWeightsWindow):
        RandomSettingsWeightsWindow.setWindowTitle(QCoreApplication.translate("RandomSettingsWeightsWindow", u"Random Settings weights", None))
    # retranslateUi

