PREFIX?=/usr
DESTDIR=
HOOKDIR=$(DESTDIR)$(PREFIX)/lib/build/obsgendiff.d

install:
	mkdir -p $(HOOKDIR)
	install -m 755 release_compare.py $(HOOKDIR)/release_compare
