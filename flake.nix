{
  description = "Multi-Campus Stage Display";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";

  outputs = { self, nixpkgs }: {

    nixosModules.default = { config, lib, pkgs, ... }:
      let
        cfg = config.services.stage-display;
      in {
        options.services.stage-display = {
          enable = lib.mkEnableOption "Multi-Campus Stage Display";

          port = lib.mkOption {
            type    = lib.types.port;
            default = 6767;
            description = "Host port the app listens on.";
          };

          dataDir = lib.mkOption {
            type    = lib.types.str;
            default = "/data/docker-appdata/stage-display";
            description = "Directory for persistent campuses.json and data.json.";
          };
        };

        config = lib.mkIf cfg.enable {

          # Seed data directory before the container starts
          systemd.services.stage-display-init = {
            description = "Initialize stage-display data files";
            wantedBy    = [ "multi-user.target" ];
            before      = [ "docker-stage-display.service" ];
            serviceConfig.Type = "oneshot";
            script = ''
              mkdir -p ${cfg.dataDir}
              [ -f ${cfg.dataDir}/data.json ]     || echo '{}' > ${cfg.dataDir}/data.json
              [ -f ${cfg.dataDir}/campuses.json ] || cp ${./campuses.json} ${cfg.dataDir}/campuses.json
            '';
          };

          virtualisation.oci-containers.containers."stage-display" = {
            image      = "ghcr.io/tristonyoder/multi-campus-stage-display:latest";
            autoStart  = true;
            log-driver = "journald";
            ports      = [ "${toString cfg.port}:6767" ];
            volumes    = [
              "${cfg.dataDir}/campuses.json:/app/campuses.json:rw"
              "${cfg.dataDir}/data.json:/app/data.json:rw"
            ];
          };
        };
      };
  };
}
