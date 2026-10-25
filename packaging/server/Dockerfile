# Hallucinate without a window, for a home server: plays through the machine's sound output, driven from the web
# interface on your phone or `hallucinate cmd`. See docs/headless.md.
#
#   docker build -f packaging/server/Dockerfile -t hallucinate .
#   docker run -d --name hallucinate -p 8483:8483 \
#     -v /path/to/music:/music:ro -v hallucinate-data:/data \
#     --device /dev/snd --group-add audio hallucinate
#   docker exec hallucinate hallucinate --pair
FROM python:3.12-slim-bookworm

# What PySide6's Qt needs at run time (no display server: nothing is drawn), and ALSA/PulseAudio for sound.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 \
      libglib2.0-0 libpulse0 libasound2 alsa-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY packaging/build-requirements.txt packaging/build-requirements.txt
# The exact, checksummed versions the release builds use
RUN pip install --no-cache-dir --require-hashes -r packaging/build-requirements.txt
COPY hallucinate hallucinate
RUN pip install --no-cache-dir --no-deps --no-build-isolation . && rm -rf /src

# Its own user; everything it keeps lives in /data (a volume), the music is read from /music
RUN useradd --system --create-home --uid 1000 --groups audio hallucinate \
 && mkdir -p /data /music && chown hallucinate /data
USER hallucinate
ENV XDG_CONFIG_HOME=/data/config XDG_DATA_HOME=/data/data XDG_CACHE_HOME=/data/cache \
    HALLUCINATE_CONTROL_SOCKET=/data/control HALLUCINATE_DISABLE_LEGACY_MIGRATION=1 \
    PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8483
# --network: inside a container the web interface must listen beyond the container itself; who can reach it is
# then up to the published port (-p). Only devices paired with a code can use it.
ENTRYPOINT ["hallucinate"]
CMD ["--headless", "--network", "/music"]
