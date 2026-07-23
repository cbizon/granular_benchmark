#!/bin/sh
set -eu

curl -L -sS -o bizon1998a.pdf \
  "https://journals.aps.org/prl/pdf/10.1103/PhysRevLett.80.57"
curl --http1.1 -L -sS -o walton-1993-chapter-25.pdf \
  "http://grainflow-dynamics.com/index_files/index_files/Simulation_Particle_Interactions_Chap25_ed_Roco.pdf"
curl -L -sS -o lubachevsky-1991-billiards.pdf \
  "https://arxiv.org/pdf/cond-mat/0503627"
curl -L -sS -o marin-risso-cordero-1993.pdf \
  "https://www.cec.uchile.cl/cinetica/pcordero/articles/JCompPhys.109.306.1993.pdf"
curl -L -sS -o rapaport-1980-event-scheduling.html \
  "https://www.sciencedirect.com/science/article/pii/0021999180901047"

shasum -a 256 ./*
