MEBS_VERSION = 0.1.0
MEBS_SITE = $(BR2_EXTERNAL_MEBS_PATH)/../mebs
MEBS_SITE_METHOD = local
MEBS_DEPENDENCIES = python3 util-linux

ifeq ($(BR2_PACKAGE_MEBS_DISPLAY),y)
MEBS_DEPENDENCIES += python-pillow freetype
endif

ifeq ($(BR2_PACKAGE_MEBS_CONTROLS),y)
MEBS_DEPENDENCIES += libdrm
define MEBS_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) -Wall -Wextra -Werror -I$(STAGING_DIR)/usr/include/libdrm $(@D)/drm_presenter.c $(TARGET_LDFLAGS) -ldrm -o $(@D)/mebs-drm
endef
define MEBS_INSTALL_DRM
	$(INSTALL) -D -m 0755 $(@D)/mebs-drm $(TARGET_DIR)/usr/bin/mebs-drm
endef
MEBS_POST_INSTALL_TARGET_HOOKS += MEBS_INSTALL_DRM
endif

define MEBS_INSTALL_TARGET_CMDS
	$(INSTALL) -d $(TARGET_DIR)/usr/lib/mebs/mebs
	$(INSTALL) -m 0644 $(@D)/*.py $(TARGET_DIR)/usr/lib/mebs/mebs/
	$(INSTALL) -D -m 0644 $(@D)/assets/mebs-logo-mask.png $(TARGET_DIR)/usr/lib/mebs/mebs/assets/mebs-logo-mask.png
	$(INSTALL) -D -m 0644 $(@D)/assets/logo-provenance.json $(TARGET_DIR)/usr/lib/mebs/mebs/assets/logo-provenance.json
	$(INSTALL) -D -m 0644 $(@D)/ui/preview.html $(TARGET_DIR)/usr/lib/mebs/mebs/ui/preview.html
	$(INSTALL) -D -m 0755 $(MEBS_PKGDIR)/mebs-launcher $(TARGET_DIR)/usr/bin/mebs
endef

$(eval $(generic-package))
