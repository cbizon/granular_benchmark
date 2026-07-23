/* 
   6/11/95 -- first revision
   9/17/95 -- implemented DSA
*/

/*Error Codes:

 0: Root not correctly bound in findroot.
 1: Root not correctly bound in findvroot.
 2: Zdetect problem.
 3: Logic problem in findvroot.
 4: Particle escape. Caught in vwall.
 5: c_calc error.
 6: cw_calc error.
 7: cv_calc error.
 8: c_add death: Out of memory.
 9: Particle escape. Caught when writing fields.

*/

#include "main.h"
#include "clist.h"
#include "collide.h"
#include "detect.h"
#include "fel.h"
#include "plist.h"
//#include "stat.h"
#include "cell.h"
#include "files.h"
#include <stdlib.h>
#include <stdio.h>
#include <iostream>
using namespace std;
#include <math.h>
#include <float.h>
#include <time.h>
#include <sys/types.h>
#include <assert.h>
#include <string.h>


#define max(x,y)     (((x) > (y)) ? (x) : (y))



int          XWindows = 0;
int          lastA = -1,  
             lastB = -1;     // last particles to collide


int           Done = 0;    /* Flag to indicate when done    */

P_DATA p[NP];    /* array of particles */
int fel[NFEL];  /* global FEL list */
C_DATA *garbage;
CellSet  TheGrid[XGSIZE][YGSIZE][ZGSIZE];
int TheNeighbors[NP];
ParamStructPtr TheParams = new ParamStruct;
FILE *list,*balls,*stats,*tracks,*pos,*vel,*restart,*starter,*plate,
     *fieldtime,*platevel;
#if ROTATIONS == 1
FILE *ome;
#endif
#if COUNTCOLS == 1
FILE *numcoll;
#endif
#if PERIODIC
FILE *crossings;
#endif

double Gtime = 0.0;	/* global event time */
double Stime;
double TimeStep = TIMESTEP;
double SysEnergy = 0.0;
long NumBallColl = 0,NumWallColl = 0,NumBottColl=0;
double vcnbar = 0.;
double BallDE = 0. , WallDE=0.,BottDE=0;
#if ROTATIONS == 1
double BallDRE=0., WallDRE=0., BottDRE=0.;
#endif
double impulse=0.;
double leftp,rightp,frontp,backp,midpx,midpy,radp;
//double clocker = 0.;
#if GAMMASWEEP == 1
int period_count = 1;
#endif
#if RESTTYPE == 1
#if GRAV == 1
double VMIN = sqrt((G*PDIAM)*1.0);
#else
double VMIN = sqrt((PDIAM)*1.0);
#endif
//double VMIN = .447214*sqrt(340./80.);
double RSLOPEB = (1-BALLREST)/pow(VMIN,0.75);
double RSLOPEW = (1-WALLREST)/pow(VMIN,0.75);
#endif
#if WALLFRICTION == 2
double RSLOPEWM = (1-WALLMU)/pow(VMIN,0.75);
#endif
double worstdt=0.;
double worstdz=0.;
#if MEASUREP ==1
int numcross[NP];
double lastx[NP];
double pofl[PL];  /*Should be even, since log(0)=-Inf*/
#endif
#if PERIODIC
double startx[NP];
double starty[NP];
double startz[NP];
int numroundx[NP];
int numroundy[NP];
int numroundz[NP];
#endif
long balle[100][100];
long walle[100][100];
int phase=0;
double pyyflux[ZGSIZE];
double pzzflux[ZGSIZE];
double pyzflux[ZGSIZE];
double pzyflux[ZGSIZE];
double loss[ZGSIZE];
double gain[ZGSIZE];
double vzbar[ZGSIZE];
int listarray[NMOV];
#if PERIODIC
double virial=0.;
double vc=0.;
#endif
#if GK == 1
Pvector vinit[NMOV]; 
Pvector Ptensor[3];
Pvector Ptensorinit[3];
double D=0.;
double eta=0.;
double lambda=0.;
double yz=0;
#endif
#ifdef TONLY 
slab TheSlabs[ZGSIZE];
#endif
#ifdef GRAVDIM
FILE *gs;
#endif

/* returns collision first collision time of local event list of particle
a.  Takes into account when local list is NULL */

double get_ctime( int a ) {
  if (p[a].cl != NULL)
    return(p[a].cl->time);
  else
    return(HUGE);
}

void grid_destroy() {
  for(int x=0;x<XGSIZE;x++)
    for(int y=0;y<YGSIZE;y++)
      for(int z=0;z<ZGSIZE;z++)
	TheGrid[x][y][z].removeall();
}

void new_collision() {
  int ParA;
  int ParB;
  double CTime;
  cout << "Particle A#";
  cin >> ParA;
  cout << "Current least collision[" << ParA << "]= " << get_ctime(ParA) << endl;
  cout << "Particle B#";
  cin >> ParB;
  cout << "Collision Time:";
  cin >> CTime;
  c_add( ParA, ParB, CTime );
}






// Add collision check time

//THIS

void simulate(int step) {
//  pl_print();
//  cl_print();
//  fel_print();
  double NextEvent,t1,deltaT;
  double deltaaT,deltabT,tempby,tempay,tempaz,tempbz,distance;
  double deltaE;
  int real,a,b,NextParticle,OtherParticle,done = 0;
  int thermalized;


  while ((Gtime < TMAX+Stime) && (done == 0)) {

/*    int b1=18,b2=17;
    double p2dt=Gtime-p[b2].time;
    double p1dt=Gtime-p[b1].time;
    double l2z=p[b2].loc.z+p[b2].vel.z*p2dt-.5*p[b2].g*p2dt*p2dt;
    double l1z=p[b1].loc.z+p[b1].vel.z*p1dt-.5*p[b1].g*p1dt*p1dt;
    double l2y=p[b2].loc.y+p[b2].vel.y*p2dt-.5*p[b2].gvec.y*p2dt*p2dt;
    double l1y=p[b1].loc.y+p[b1].vel.y*p1dt-.5*p[b1].gvec.y*p1dt*p1dt;
    double disty=l2y-l1y;
    double distz=l2z-l1z;
    double dist=sqrt(disty*disty+distz*distz)-.5*(p[b1].diam+p[b2].diam);
    if (dist < 0.01)
     fprintf(stdout,"at %f dist is %g\n",Gtime,dist); 
    if (dist < -.0001){
     fprintf(stdout,"die now\n");
     fprintf(stdout,"Particle %d\n",b1);
     fprintf(stdout,"+=============+\n");
     fprintf(stdout,"Position: %f %f \n",p[b1].loc.y,p[b1].loc.z);
     fprintf(stdout,"Velocity: %f %f \n",p[b1].vel.y,p[b1].vel.z);
     fprintf(stdout,"Accelera: %f %f \n",p[b1].gvec.y,p[b1].gvec.z);
     fprintf(stdout,"Time:     %f\n\n",p[b1].time);
     fprintf(stdout,"Particle %d\n",b2);
     fprintf(stdout,"+=============+\n");
     fprintf(stdout,"Position: %f %f \n",p[b2].loc.y,p[b2].loc.z);
     fprintf(stdout,"Velocity: %f %f \n",p[b2].vel.y,p[b2].vel.z);
     fprintf(stdout,"Accelera: %f %f \n",p[b2].gvec.y,p[b2].gvec.z);
     fprintf(stdout,"Time:     %f\n\n",p[b2].time);
     assert(0);
    }
*/



/*    int b2=403;
    double p2dt=Gtime-p[b2].time;
    double l2y=p[b2].loc.y+p[b2].vel.y*p2dt-.5*p[b2].gvec.y*p2dt*p2dt;
    if ((l2y>p[b2].cell.y) || (l2y <p[b2].cell.y-1)){
     fprintf(stdout,"Particle %d\n",b2);
     fprintf(stdout,"+=============+\n");
     fprintf(stdout,"Position: %f %f \n",p[b2].loc.y,p[b2].loc.z);
     fprintf(stdout,"Velocity: %f %f \n",p[b2].vel.y,p[b2].vel.z);
     fprintf(stdout,"Accelera: %f %f \n",p[b2].gvec.y,p[b2].gvec.z);
     fprintf(stdout,"Time:     %f\n\n",p[b2].time);
     assert(0);
    }
*/


    a = NextParticle = fel[0];
    b = OtherParticle = p[NextParticle].cl->b;
    while (c_valid(a,b) == 0) {
      c_delete(a);
      fel_resort(a);
      a = NextParticle = fel[0];
      b = OtherParticle = p[NextParticle].cl->b;

    } 
    NextEvent = p[NextParticle].cl->time;
    if (p[a].pty == WALL){
      Gtime = NextEvent;
#ifdef TONLY
      slab_remove(OtherParticle);
#endif      
      if (p[b].pty == SPHERE){
	ballwall(NextParticle,0,&real);
	if (real != 0){
	  lel_destroy(OtherParticle,0);
	  c_calc(OtherParticle,0);
          fel_resort(OtherParticle);
          c_delete(a);
	}
	else
	  c_delete(a);
#ifdef TONLY
      slab_add(OtherParticle);
#endif      
      }
      else {
        printf("WALL CROSSING!!, %i has gone to -- \n",p[a].cell.z);
	if (b == TheParams->plusz)
	  p[a].cell.z +=1;
	if (b == TheParams->negz)
	  p[a].cell.z -=1;
        printf(" - %i\n",p[a].cell.z);
	lel_destroy(a,0);
	cw_calc(0);
      }
      fel_resort(a);
      done=step;
    }
    else {
      switch (p[b].pty) {
      case SPHERE:
#if FOLLOW == 1
        if ((a == THIS) || (b == THIS))
          fprintf(stdout,"\nBall Ball: %d %d %g\n",a,b,NextEvent);
#endif
	evolve(a,NextEvent,0);
	evolve(b,NextEvent,0);
	Gtime = NextEvent;
#ifdef TONLY
        slab_remove(a);
        slab_remove(b);
#endif
	deltaE=ballball(NextParticle,0);
//        if ((425==b && 1642==a) || (1642==b && 425==a))
//          fprintf(stdout,"Collided 1 and 2 at %f\n",Gtime);
#if THERMAL3 == 1
        feedback(deltaE,a,b); 
#endif        
#ifdef TONLY
        slab_add(a);
        slab_add(b);
#endif
#if THERMAL4 == 1
/*      if ((a == b1 && b == b2) || (a == b2 && b == b1))
         fprintf(stdout,"%d\n",deltaE);*/
/*      if (deltaE < 1e-9){
        fluctforce(a,b); 
       }
      else*/
        fluctforce(-1,-1);
#endif
	lel_destroy(NextParticle,0);
	lel_destroy(OtherParticle,0);
	c_calc(NextParticle,0);
	c_calc(OtherParticle,0);
	fel_resort(a);
        fel_resort(b);
	done = step;
        break;
      case WALL:
#if FOLLOW == 1
        if ((a == THIS) || (b == THIS))
	   fprintf(stdout,"\nBall Wall: %d %d %g\n",a,b,NextEvent);
#endif
	Gtime = NextEvent;
#ifdef TONLY
        slab_remove(a);
#endif
	ballwall(NextParticle,0,&real);
#ifdef TONLY
        slab_add(a);
#endif
        if (real != 0){
	  lel_destroy(NextParticle,0);
	  c_calc(NextParticle,1);
        }
	else
	  c_delete(a);
	fel_resort(a);
	done = step;
	TheParams->CPUTime += deltaT;
	break;
      case VWALL:
	Gtime = NextEvent;
	vwall(NextParticle,0);
	cv_calc(NextParticle,b,0);
	fel_resort(a);
	done = step;
	break;
      case STAT:
	Gtime = NextEvent;
	statstat(NextParticle);
	lel_destroy(NextParticle,0);
	cs_calc(NextParticle);
	//      tree_resort(NextParticle);
	fel_resort(NextParticle);
	done = step;
	break;
#if THERMAL == 1
      case THERM:
//        fprintf(stdout,"Thermalizing particle %i\n",a);
	Gtime = NextEvent;
        thermalize(NextParticle,b);
        lel_destroy(NextParticle,0); 
        c_calc(NextParticle,0);
	fel_resort(NextParticle);
        done=step;
        break;
#endif
      }
    }
//    if (a == 9 || b == 9) {
//    printf("%i x=%f, y=%f, z=%f\n",a,p[a].loc.x,p[a].loc.y,p[a].loc.z);
//    printf("%i yv=%f zv=%f g=%f\n",a,p[a].vel.y,p[a].vel.z,p[a].g);
//    printf("%i b=%i, time=%f, Gtime=%f\n",a,b,NextEvent,Gtime);
//    printf("%i xc=%i, yc=%i, zc=%i\n\n",a,p[a].cell.x,p[a].cell.y,p[a].cell.z,a);
/*    deltaaT = Gtime - p[8].time;
    deltabT = Gtime - p[65].time;
    tempaz = p[8].loc.z + p[8].vel.z * deltaaT - .5 * p[8].g * deltaaT *deltaaT;
    tempbz = p[65].loc.z + p[65].vel.z * deltabT - .5 * p[65].g * deltabT * deltabT;
    tempay = p[8].loc.y + p[8].vel.y * deltaaT;
    tempby = p[65].loc.y + p[65].vel.y * deltabT;
    distance = sqrt((tempaz-tempbz)*(tempaz-tempbz)+(tempay-tempby)*(tempay-tempby));
    printf("Wall at %f \n",temp12z);
    printf("Distance between 8 and 65 - pdiam: %g \n",distance-TheParams->pdiam);
    deltabT = Gtime - p[36].time;
    tempbz = p[36].loc.z + p[36].vel.z * deltabT - .5 * p[36].g * deltabT * deltabT;
    tempby = p[36].loc.y + p[36].vel.y * deltabT;
    distance = sqrt((tempaz-tempbz)*(tempaz-tempbz)+(tempay-tempby)*(tempay-tempby));
    printf("Distance between 8 and 36 - pdiam: %g \n",distance-TheParams->pdiam);
    deltabT = Gtime - p[LWALL].time;
    tempbz = p[LWALL].loc.z + deltabT * p[LWALL].vel.z;
    printf("16's height from the wall: %g\n\n",tempaz-tempbz);
    } */


  }
}


// simulation main loop -- text mode
void MainLoop() {

    fprintf(stdout,"At the main Loop\n");
    int ok = 0;
//    static clock_t timediff = 0;
    //open_files();
//    fprintf(stdout,"Files Opened\n");
    if (START == 1)
       ok = check_restart();
    fprintf(stdout,"OK:%d\n",ok);
    pl_init();
    fprintf(stdout,"pl_initiated\n");
    cl_calc(0);
    fprintf(stdout,"cl_calculated\n");
    fel_sort(0);
    fprintf(stdout,"fel_sorted\n");
    first_write(ok);
    fprintf(stdout,".list Written\n"); 
//    clock();
    statstat(TheParams->fstat); 
    statstat(TheParams->fstat+2);
    simulate(0);
    statstat(TheParams->fstat);
    statstat(TheParams->fstat+2);
    fprintf(stdout,"simulation finished\n");
    fprintf(stdout,"Worst z: %g, Worst dt: %g\n",worstdz,worstdt);
    last_writes();
//    do_stats();
//    timediff = clock();
//    fprintf(stderr,"Elapsed time: %f sec.\n", (double) timediff / 1000000);
}





int main(int argc, char **argv) {
      TheParams->maxball = TheParams->nball = NMOV;
      TheParams->fball = FMOV;
      TheParams->lball = LMOV;
      TheParams->nwall = NWALL;
      TheParams->fwall = FWALL;
      TheParams->lwall = LWALL;
      TheParams->nvwall = NVWALL;
      TheParams->fvwall = FVWALL;
      TheParams->lvwall = LVWALL;
      TheParams->nstat = NSTAT;
      TheParams->fstat = FSTAT;
      TheParams->lstat = LSTAT;
      TheParams->fjunk = FJUNK;
      TheParams->njunk = NJUNK;
      TheParams->ljunk = LJUNK;
      TheParams->plusx = PLUSX;
      TheParams->negx = NEGX;
      TheParams->plusy = PLUSY;
      TheParams->negy = NEGY;
      TheParams->plusz = PLUSZ;
      TheParams->negz = NEGZ;
      TheParams->pdiam = PDIAM;
      TheParams->DiamStep = PDIAM / 10;
      TheParams->NumVwall = 0;
      TheParams->StopOnError = 1; 
      TheParams->CPUStat = 1;
      TheParams->g = G;
      TheParams->pclist = 0;
      TheParams->BallRest = BALLREST;
      TheParams->WallRest = WALLREST;
      TheParams->Period = PERIOD;
      TheParams->Ampl = AMPL;
      TheParams->View3D = 0;
      TheParams->osc = OSC;
#if PLATEMOVE == 1
      TheParams->WallVel = AMPL*OMEGA;
      TheParams->Omega = OMEGA;
#else if PLATEMOVE == 0
      TheParams->WallVel = 0;
      TheParams->Omega = 0;
#endif
      TheParams->wphi = WPHI;
      TheParams->glinit = 0;
#if PLATEMOVE == 1
      TheParams->TimeOne = TIMEONE;
#else if PLATEMOVE == 0 || PLATEMOVE == -1
      TheParams->TimeOne = 0;
#endif
#if ((BALLFRICTION == 1) || (BALLFRICTION == 2) || (ROTATIONS == 1))
      TheParams->bmu = BALLMU;
#endif
#if ((WALLFRICTION == 1) || (WALLFRICTION == 2) || (ROTATIONS == 1))
      TheParams->wmu = WALLMU;
#endif
#if (ROTATIONS == 1)
      TheParams->beta0b = BETA0BALL;
      TheParams->beta0w = BETA0WALL;
#endif
#if (THERMAL == 1 || THERMAL2 == 1 || THERMAL3 == 1 || THERMAL4 == 1)
      TheParams->sigb = SIGB;
      TheParams->sigt = SIGT;
      TheParams->sigm = SIGM;
#endif
#if (THERMAL == 1)
      TheParams->ntherm=NTHERM;
      TheParams->ptherm=PTHERM;
#endif
#if (LUDING == 1)
      TheParams->cutoff = CUTOFF;
#endif

fprintf(stdout,"Set TheParams->Everything\n");

  for (int i=0;i<100;i++) 
    for (int j=0;j<100;j++) {
      walle[i][j]=0;
      balle[i][j]=0;
    }
  
  for (int i=0;i<NMOV;i++)
    listarray[i]=i;

  for (int i=0;i<ZGSIZE;i++){
     pyyflux[i]=0;
     pyzflux[i]=0;
     pzyflux[i]=0;
     pzzflux[i]=0;
     loss[i]=0.;
     gain[i]=0.;
  }

// define some local variables 
    int c_next, s_done = 0;
    double s_time = 0.0;
    Gtime = 0.0;
    NumBallColl = NumWallColl = 0;

// parse command line options 


fprintf(stdout,"Set Variables, check X\n");

// see if we're running on X 
    if (0 == 0) {
        fprintf(stdout, "No display found, using text mode.\n");
        XWindows = 0;
        open_files();
	MainLoop();
    }
    else {
      XWindows = 1;
      fprintf(stdout,"Going to use Xwindows\n");
      pl_init();
      fprintf(stdout,"Particle List Initialized\n");
      cl_calc(0);
      fprintf(stdout,"Collision Lists Calculated\n");
      fel_sort(0);
      fprintf(stdout,"Fel sorted\n");
      TimeStep = TIMESTEP;
      fprintf(stdout,"setting timestep to %f\n",TimeStep);
      TheParams->a = 0;
      TheParams->b = 1;
      TheParams->etime = 0.05;
      //SetupXWindows(argc,argv);
      //XMainLoop();
      //if (TheParams->glinit == 1)
//	the_gl_close();
    }
}


