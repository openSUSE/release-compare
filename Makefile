PREFIX?=/usr
DESTDIR=
HOOKDIR=$(DESTDIR)$(PREFIX)/lib/build/obsgendiff.d

install:
	mkdir -p $(HOOKDIR)
	install -m 755 create_changelog $(HOOKDIR)
	cp -r release_compare $(HOOKDIR)
