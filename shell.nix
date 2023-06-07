let
  nixpkgs = builtins.fetchGit { url = "https://github.com/NixOS/nixpkgs.git"; rev = "384b898d18b0044165b23d19cb9a0b8982d82b11"; };
  pkgs = import nixpkgs { };
in
pkgs.mkShell {
  nativeBuildInputs = with pkgs; [
    jekyll
    rubyPackages.jekyll-feed
    rubyPackages.jekyll-paginate
    python310
    texlive.combined.scheme-medium
  ];
}
