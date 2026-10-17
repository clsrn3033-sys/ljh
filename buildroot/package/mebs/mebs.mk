MEBS_VERSION = 0.1.0
MEBS_SITE = $(BR2_EXTERNAL_MEBS_PATH)/../mebs
MEBS_SITE_METHOD = local
MEBS_DEPENDENCIES = python3 util-linux

ifeq ($(BR2_PACKAGE_MEBS_DISPLAY),y)
MEBS_DEPENDENCIES += python-pillow freetype
endif

define MEBS_INSTALL_TARGET_CMDS
	$(INSTALL) -d $(TARGET_DIR)/usr/lib/mebs/mebs
	$(INSTALL) -m 0644 $(@D)/*.py $(TARGET_DIR)/usr/lib/mebs/mebs/
	$(INSTALL) -D -m 0644 $(@D)/ui/preview.html $(TARGET_DIR)/usr/lib/mebs/mebs/ui/preview.html
	$(INSTALL) -D -m 0755 $(MEBS_PKGDIR)/mebs-launcher $(TARGET_DIR)/usr/bin/mebs
endef

$(eval $(generic-package))
