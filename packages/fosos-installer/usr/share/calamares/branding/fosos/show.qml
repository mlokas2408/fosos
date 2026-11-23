import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation
{
    id: presentation

    function onActivate() {
        presentation.currentSlide = 0;
    }

    function onLeave() {
    }

    Timer {
        id: advanceTimer
        interval: 8000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Image {
            anchors.fill: parent
            source: "slide1.png"
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
        }
    }

    Slide {
        Image {
            anchors.fill: parent
            source: "slide2.png"
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
        }
    }

    Slide {
        Image {
            anchors.fill: parent
            source: "slide3.png"
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
        }
    }

    Slide {
        Image {
            anchors.fill: parent
            source: "slide4.png"
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
        }
    }
}
