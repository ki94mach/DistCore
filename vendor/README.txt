# DistCore needs ODBC libraries; your other Python Docker image does not.
# Use Debian 12 (bookworm) .debs — base image is python:3.12-slim-bookworm.
#
# On Windows PowerShell (with internet), from the DistCore repo:
#
#   New-Item -ItemType Directory -Force vendor | Out-Null
#   $odbc = "https://deb.debian.org/debian/pool/main/u/unixodbc"
#   $ver  = "2.3.11-2+deb12u1"
#   foreach ($f in @(
#     "libodbc2_${ver}_amd64.deb",
#     "libodbccr2_${ver}_amd64.deb",
#     "libodbcinst2_${ver}_amd64.deb",
#     "odbcinst_${ver}_amd64.deb",
#     "unixodbc-common_${ver}_all.deb",
#     "unixodbc_${ver}_amd64.deb",
#     "unixodbc-dev_${ver}_amd64.deb"
#   )) { Invoke-WebRequest "$odbc/$f" -OutFile "vendor\$f" -UseBasicParsing }
#
#   # Required transitive dependency of libodbc2 / libodbcinst2:
#   Invoke-WebRequest `
#     "https://deb.debian.org/debian/pool/main/libt/libtool/libltdl7_2.4.7-7~deb12u1_amd64.deb" `
#     -OutFile "vendor\libltdl7_2.4.7-7~deb12u1_amd64.deb" -UseBasicParsing
#
#   Invoke-WebRequest `
#     "https://packages.microsoft.com/debian/12/prod/pool/main/m/msodbcsql17/msodbcsql17_17.11.1.1-1_amd64.deb" `
#     -OutFile "vendor\msodbcsql17_17.11.1.1-1_amd64.deb" -UseBasicParsing
#
# Copy vendor\*.deb to the server, sync Dockerfile, then:
#   docker compose build --no-cache && docker compose up -d
