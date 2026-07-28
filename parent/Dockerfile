FROM odoo:18.0

USER root

# create venv and install python deps there (avoids Debian-managed packages)
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-venv \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir \
      psycopg2-binary \
      PyJWT \
      anthropic

# make venv default for python/pip
ENV PATH="/opt/venv/bin:$PATH"

USER odoo
