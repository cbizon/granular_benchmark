#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "main.h"

P_DATA p[NP];
ParamStructPtr TheParams;
double Gtime = 0.0;
long NumBallColl = 0;
long NumWallColl = 0;
long NumBottColl = 0;
double BallDE = 0.0;
double WallDE = 0.0;
double BottDE = 0.0;
double BallDRE = 0.0;
double WallDRE = 0.0;
double BottDRE = 0.0;
double VMIN = 0.0;
double RSLOPEB = 0.0;
double RSLOPEW = 0.0;
double vcnbar = 0.0;
double impulse = 0.0;
double leftp = 0.0;
double rightp = 0.0;
double frontp = 0.0;
double backp = 0.0;
double midpx = 0.0;
double midpy = 0.0;
double radp = 0.0;
double SysEnergy = 0.0;
double gain[ZGSIZE] = {};
double loss[ZGSIZE] = {};
int listarray[NMOV] = {};
long walle[101][100] = {};
long balle[101][100] = {};
int phase = 0;
double pyyflux[ZGSIZE] = {};
double pyzflux[ZGSIZE] = {};
double pzyflux[ZGSIZE] = {};
double pzzflux[ZGSIZE] = {};
double vzbar[ZGSIZE] = {};
FILE *stats = nullptr;
FILE *tracks = nullptr;
FILE *pos = nullptr;
FILE *vel = nullptr;
FILE *restart = nullptr;
FILE *starter = nullptr;
FILE *plate = nullptr;
FILE *ome = nullptr;
void *TheGrid = nullptr;
void *TheNeighbors = nullptr;

extern void ballwall(int a, int debug, int *real);

static void set_vector(PVECTOR *value, double x, double y, double z) {
  value->x = x;
  value->y = y;
  value->z = z;
}

int main() {
  TheParams = static_cast<ParamStructPtr>(
      calloc(1, sizeof(struct ParamStruct)));
  if (TheParams == nullptr) {
    return 2;
  }

  TheParams->WallRest = 0.7;
  TheParams->BallRest = 0.7;
  TheParams->g = 1.0;
  TheParams->pdiam = PDIAM;
  TheParams->fwall = FWALL;
  TheParams->lwall = LWALL;
  TheParams->Ampl = 1.0;
  TheParams->Omega = 1.0;
  TheParams->Period = 2.0 * PI;
  TheParams->WallVel = 1.0;
  VMIN = sqrt(PDIAM);
  RSLOPEB = (1.0 - TheParams->BallRest) / pow(VMIN, 0.75);
  RSLOPEW = (1.0 - TheParams->WallRest) / pow(VMIN, 0.75);

  static C_DATA node;
  double diameter;
  double mu;
  double beta0;
  double drive_phase;
  double vx;
  double vy;
  double vz;
  double wx;
  double wy;
  double wz;

  while (scanf(
             "%lf %lf %lf %lf %lf %lf %lf %lf %lf %lf",
             &diameter,
             &mu,
             &beta0,
             &drive_phase,
             &vx,
             &vy,
             &vz,
             &wx,
             &wy,
             &wz) == 10) {
    TheParams->wmu = mu;
    TheParams->beta0w = beta0;

    const int wall = LWALL;
    const double angle = 2.0 * PI * drive_phase;
    p[wall].g = TheParams->g;
    p[wall].time = Gtime - angle;
    p[wall].diam = 0.0;
    p[wall].c = 0;
    p[wall].pty = 1;
    set_vector(&p[wall].vel, 0.0, 0.0, 0.0);
    set_vector(&p[wall].loc, 0.0, 0.0, 0.0);
    set_vector(&p[wall].norm, 0.0, 0.0, -1.0);

    p[0].g = TheParams->g;
    p[0].time = Gtime;
    p[0].c = 0;
    p[0].pty = 0;
    p[0].wallcalc = 0;
    p[0].diam = diameter;
    const double contact_z = sin(angle) + diameter / 2.0;
    set_vector(&p[0].loc, 5.5, 5.5, contact_z);
    p[0].cell.x = 6;
    p[0].cell.y = 6;
    p[0].cell.z = static_cast<int>(ceil(contact_z));
    set_vector(&p[0].vel, vx, vy, vz);
    set_vector(&p[0].ome, wx, wy, wz);

    node.b = wall;
    node.time = Gtime;
    node.cb = 0;
    node.cnext = nullptr;
    p[0].cl = &node;

    int real = 0;
    ballwall(0, 0, &real);
    printf(
        "%d %.17g %.17g %.17g %.17g %.17g %.17g\n",
        real,
        p[0].vel.x,
        p[0].vel.y,
        p[0].vel.z,
        p[0].ome.x,
        p[0].ome.y,
        p[0].ome.z);
  }
  free(TheParams);
  return 0;
}

void fel_resort(int) {}
void open_files() {}
void open_stats() {}
void close_files() {}
void write_restart() {}
void cl_calc(int) {}
void pl_init() {}
void fel_sort(int) {}
void bomb(int, int) { exit(9); }
void last_writes() {}
double vdetect(int, int) { return 0.0; }
double detect(int, int) { return 0.0; }
void c_add(int, int, double) {}
void close_stats() {}
void lel_destroy(int, int) {}
void c_calc(int, int) {}
void cw_calc(int) {}
double c3detect(int, int) { return 0.0; }
void c_delete(int) {}
