#!/bin/sh
# FosOS Desktop session for xrdp. Applied to /etc/xrdp/startwm.sh on enable.
# Match Debian xrdp startwm environment loading, then run fosos-session.

# Rely on /etc/pam.d/xrdp-sesman using pam_env to load locale/environment.
if test -r /etc/profile; then
	# shellcheck disable=SC1091
	. /etc/profile
fi
if test -r "$HOME/.profile"; then
	# shellcheck disable=SC1090
	. "$HOME/.profile"
fi

export XDG_CURRENT_DESKTOP=FosOS
export XDG_SESSION_DESKTOP=fosos-desktop
export DESKTOP_SESSION=fosos-desktop
export GTK_THEME=FosOS
export GTK_ICON_THEME_NAME=FosOS

if [ -z "${XDG_CONFIG_DIRS}" ]; then
	XDG_CONFIG_DIRS="/etc/xdg"
fi
case ":${XDG_CONFIG_DIRS}:" in
*:/etc/xdg/fosos-desktop:*) ;;
*) XDG_CONFIG_DIRS="/etc/xdg/fosos-desktop:${XDG_CONFIG_DIRS}" ;;
esac
export XDG_CONFIG_DIRS

if command -v fosos-session >/dev/null 2>&1; then
	exec fosos-session
fi

test -x /etc/X11/Xsession && exec /etc/X11/Xsession
exec /bin/sh /etc/X11/xinit/xinitrc
