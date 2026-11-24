import QtQuick
import calamares.slideshow 1.0

Presentation
{
    id: presentation

    function onActivate() {
        presentation.currentSlide = 0;
        advanceTimer.restart();
    }

    function onLeave() {
        advanceTimer.stop();
    }

    Timer {
        id: advanceTimer
        interval: 7000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#0a0a0a"
        }
        Image {
            anchors.fill: parent
            source: "slide1.png"
            fillMode: Image.PreserveAspectFit
            asynchronous: false
            smooth: true
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#0a0a0a"
        }
        Image {
            anchors.fill: parent
            source: "slide2.png"
            fillMode: Image.PreserveAspectFit
            asynchronous: false
            smooth: true
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#0a0a0a"
        }
        Image {
            anchors.fill: parent
            source: "slide3.png"
            fillMode: Image.PreserveAspectFit
            asynchronous: false
            smooth: true
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#0a0a0a"
        }
        Image {
            anchors.fill: parent
            source: "slide4.png"
            fillMode: Image.PreserveAspectFit
            asynchronous: false
            smooth: true
        }
    }
}
