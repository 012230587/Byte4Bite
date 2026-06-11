# Forward all make targets to byte4bite/
.PHONY: all
%:
	@$(MAKE) -C byte4bite $@
