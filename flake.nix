{
  # Hallucinate on Nix and NixOS: `nix run github:Phosphene-dev/Hallucinate`, or add
  # `inputs.hallucinate.packages.${system}.default` to environment.systemPackages / home.packages.
  # Built from source against nixpkgs' own Python, PySide6 and Qt.
  description = "A fast desktop music player for the music you own";

  inputs.nixpkgs.url = "https://channels.nixos.org/nixos-unstable/nixexprs.tar.xz";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in {
      packages = forAll (pkgs: rec {
        default = hallucinate;
        hallucinate = pkgs.python3Packages.buildPythonApplication {
          pname = "hallucinate";
          version = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version;
          pyproject = true;
          src = nixpkgs.lib.cleanSource ./.;

          # nixpkgs' setuptools can trail the newest by a release; any recent one builds this
          postPatch = ''
            substituteInPlace pyproject.toml --replace-fail '"setuptools>=84.0.0"' '"setuptools"'
          '';
          build-system = [ pkgs.python3Packages.setuptools ];
          dependencies = with pkgs.python3Packages; [ pyside6 mutagen keyring numpy ];
          nativeBuildInputs = [ pkgs.qt6.wrapQtAppsHook ];
          # Qt's plugins (Wayland, the FFmpeg audio backend) and QML modules, found through the wrapper
          buildInputs = with pkgs.qt6; [ qtbase qtdeclarative qtmultimedia qtwayland qtsvg ];

          # The Python wrapper and the Qt wrapper, in one
          dontWrapQtApps = true;
          preFixup = ''makeWrapperArgs+=("''${qtWrapperArgs[@]}" --set-default HALLUCINATE_PACKAGE nix)'';

          postInstall = ''
            install -Dm644 packaging/hallucinate.desktop $out/share/applications/hallucinate.desktop
            cp -r packaging/icons $out/share/icons
          '';

          # the test suite needs a display, audio and a session bus: CI runs it
          doCheck = false;
          pythonImportsCheck = [ "hallucinate" ];

          meta = {
            description = "A fast desktop music player for the music you own";
            homepage = "https://github.com/Phosphene-dev/Hallucinate";
            license = nixpkgs.lib.licenses.mit;
            mainProgram = "hallucinate";
            platforms = systems;
          };
        };
      });

      apps = forAll (pkgs: {
        default = { type = "app"; program = "${self.packages.${pkgs.system}.default}/bin/hallucinate"; };
      });
    };
}
