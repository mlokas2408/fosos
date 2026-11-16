import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation
{
    id: presentation

    Timer {
        interval: 8000
        running: true
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Rectangle { anchors.fill: parent; color: "#0a0a0a" }
        Text {
            anchors.centerIn: parent
            width: parent.width * 0.82
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            color: "#fafafa"
            font.family: "Inter"
            font.pointSize: 16
            text: "Installing FosOS.\nFirefox is the browser. Choose a language, keyboard, disk, and account."
        }
    }

    Slide {
        Rectangle { anchors.fill: parent; color: "#0a0a0a" }
        Text {
            anchors.centerIn: parent
            width: parent.width * 0.82
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            color: "#fafafa"
            font.family: "Inter"
            font.pointSize: 16
            text: "Erase the disk, or partition it yourself.\nEncryption is available. The machine then reboots into the account you created."
        }
    }
}
