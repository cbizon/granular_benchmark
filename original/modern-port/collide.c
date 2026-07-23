#include "main.h"
#include "math.h"
#include "assert.h"
#include "cell.h"
#include "clist.h"
#include "collide.h"
#include "fel.h"
#include "files.h"
#include "collide.h"
#include "plist.h"
#include <iostream>
using namespace std;
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>

extern P_DATA p[];
extern long NumBallColl;
extern long NumWallColl;
extern long NumBottColl;
extern double BallDE;
extern double WallDE;
extern double BottDE;
extern double vcnbar;
#if ROTATIONS == 1
extern double BallDRE;
extern double WallDRE;
extern double BottDRE;
#endif
extern double impulse;
extern double leftp,rightp,frontp,backp,midpx,midpy,radp;
extern double Gtime;
extern double SysEnergy;
extern CellSet TheGrid[XGSIZE][YGSIZE][ZGSIZE];
extern int TheNeighbors[NP];
extern ParamStructPtr TheParams;
extern FILE *stats,*tracks,*pos,*vel,*plate;
#if COUNTCOLS == 1
extern FILE *numcoll;
#endif
#if ROTATIONS == 1
extern FILE *ome;
#endif
#if PERIODIC == 1 || PERIODIC == 2 || PERIODIC == 3
extern FILE *crossings;
#endif
//extern double clocker;
#if GAMMASWEEP == 1 
extern period_count;
#endif
#if RESTTYPE == 1
extern double VMIN,RSLOPEB,RSLOPEW;
#endif
#if WALLFRICTION == 2
extern double RSLOPEWM;
#endif
#if MEASUREP == 1
extern double pofl[],lastx[];
extern int numcross[];
#endif
#if PERIODIC == 1 || PERIODIC == 2 || PERIODIC == 3
extern double startx[];
extern double starty[];
extern double startz[];
extern int numroundx[];
extern int numroundy[];
extern int numroundz[];
#endif
extern long walle[101][100];
extern long balle[101][100];
extern int phase;
extern double pyyflux[ZGSIZE];
extern double pzzflux[ZGSIZE];
extern double pyzflux[ZGSIZE];
extern double pzyflux[ZGSIZE];
extern double loss[ZGSIZE];
extern double gain[ZGSIZE];
extern double vzbar[ZGSIZE];
extern int listarray[NMOV];
#if PERIODIC == 3
extern double virial,vc;
#endif
#if GK == 1
extern Pvector vinit[NMOV]; 
extern Pvector Ptensor[3];
extern Pvector Ptensorinit[3];
extern double D;
extern double eta;
extern double lambda;
extern double yz;
#endif
#ifdef TONLY
extern slab TheSlabs[ZGSIZE];
#endif
#ifdef GRAVDIM
extern double totgy,totgz;
extern FILE *gs;
#endif

static inline int allocated_grid_cell_exists(int x, int y, int z) {
  return x >= 0 && x < XGSIZE
      && y >= 0 && y < YGSIZE
      && z >= 0 && z < ZGSIZE;
}

static inline int physical_grid_cell_exists(int x, int y, int z) {
  return x >= 1 && x <= XBSIZE
      && y >= 1 && y <= YBSIZE
      && z >= 1 && z <= ZBSIZE;
}

inline double dot(PVECTOR a, PVECTOR b){
  return(a.x*b.x+a.y*b.y+a.z*b.z);
}

#if ROTATIONS != 1
int ballball(int a, int debug) {
  PVECTOR urab,urba,vanf,van,vaetc,vbnf,vbn,vbetc;
  PVECTOR vat,vbt,utab,vt,vatf,vbtf;
  double magnitude,alpha,beta,dumbdot;
  double tstep,tnew,velmag,dt,tay,tbz,tby,taz;
  double tl, tr, tc,oldm,vsqr,rest,dvt,mag;
  double IE,FE;
  int i=0;
  NumBallColl++;


  int b = p[a].cl->b;

  IE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z)+(p[b].vel.x*p[a].vel.x) + (p[b].vel.y*p[b].vel.y)+(p[b].vel.z*p[b].vel.z));

  urab.x = p[b].loc.x - p[a].loc.x;
  urab.y = p[b].loc.y - p[a].loc.y;
  urab.z = p[b].loc.z - p[a].loc.z;
  magnitude = sqrt(urab.x * urab.x + urab.y * urab.y + urab.z * urab.z);

  if (magnitude != 0) {
    urab.x /= magnitude;
    urab.y /= magnitude;
    urab.z /= magnitude;
  }
    
  urba.x = -(urab.x);
  urba.y = -(urab.y);
  urba.z = -(urab.z);
  
  dumbdot = p[a].vel.x * urab.x + p[a].vel.y * urab.y + p[a].vel.z * urab.z;
  
  van.x = dumbdot * urab.x;
  van.y = dumbdot * urab.y;
  van.z = dumbdot * urab.z;
  
  vaetc.x = p[a].vel.x - van.x;
  vaetc.y = p[a].vel.y - van.y;
  vaetc.z = p[a].vel.z - van.z;
  
  dumbdot = p[b].vel.x * urab.x + p[b].vel.y * urab.y + p[b].vel.z * urab.z;
  vbn.x = dumbdot * urab.x;
  vbn.y = dumbdot * urab.y;
  vbn.z = dumbdot * urab.z;
  
  vbetc.x = p[b].vel.x - vbn.x;
  vbetc.y = p[b].vel.y - vbn.y;
  vbetc.z = p[b].vel.z - vbn.z;


  vsqr=(vbn.x-van.x)*(vbn.x-van.x)+(vbn.y-van.y)*(vbn.y-van.y)+(vbn.z-van.z)*(vbn.z-van.z);

#if BALLFRICTION == 1
  
  vt.x = vaetc.x - vbetc.x;
  vt.y = vaetc.y - vbetc.y;
  vt.z = vaetc.z - vbetc.z;

  mag = sqrt(vt.x * vt.x + vt.y*vt.y + vt.z*vt.z);

  if (mag != 0.){
    utab.x = vt.x/mag;
    utab.y = vt.y/mag;
    utab.z = vt.z/mag;}

  dumbdot = vaetc.x * utab.x + vaetc.y * utab.y + vaetc.z * utab.z;
  
  vat.x = dumbdot * utab.x;
  vat.y = dumbdot * utab.y;
  vat.z = dumbdot * utab.z;
  
  vaetc.x = vaetc.x - vat.x;
  vaetc.y = vaetc.y - vat.y;
  vaetc.z = vaetc.z - vat.z;

  dumbdot = vbetc.x * utab.x + vbetc.y * utab.y + vbetc.z * utab.z;

  vbt.x = dumbdot * utab.x;
  vbt.y = dumbdot * utab.y;
  vbt.z = dumbdot * utab.z;
  
  vbetc.x = vbetc.x - vbt.x;
  vbetc.y = vbetc.y - vbt.y;
  vbetc.z = vbetc.z - vbt.z;

  dvt = TheParams->bmu * sqrt(vsqr);

  if (mag > dvt){
    vt.x = .5 * utab.x * dvt;
    vt.y = .5 * utab.y * dvt;
    vt.z = .5 * utab.z * dvt;}
  else{
    vt.x = .5 * utab.x * mag;
    vt.y = .5 * utab.y * mag;
    vt.z = .5 * utab.z * mag;}
  
  vatf.x = vat.x - vt.x;
  vatf.y = vat.y - vt.y;
  vatf.z = vat.z - vt.z;
  vbtf.x = vbt.x + vt.x;
  vbtf.y = vbt.y + vt.y;
  vbtf.z = vbt.z + vt.z;
  vaetc.x += vatf.x;
  vaetc.y += vatf.y;
  vaetc.z += vatf.z;
  vbetc.x += vbtf.x;
  vbetc.y += vbtf.y;
  vbetc.z += vbtf.z;
  
#endif
 
#if RESTTYPE == 0
  alpha = 1 - TheParams->BallRest;
  beta = 1 + TheParams->BallRest;
#else if RESTTYPE == 1
  if (vsqr > VMIN * VMIN) {
    alpha = 1 - TheParams->BallRest;
    beta = 1 + TheParams->BallRest;
  }
  else  {
    rest=1-RSLOPEB*pow(vsqr,0.375);
/*  Logic here seems fine.  
    assert (rest >= TheParams->BallRest);
    assert (rest <= 1.0);*/
    alpha = 1-rest;
    beta = 1+rest;
#if FOLLOW == 1
    if (a == THIS || b == THIS){ 
     fprintf(stdout,"Colliding particles with a restitution of %f at %f\n",rest,Gtime);
     fprintf(stdout,"Particle THIS at %f\n",p[i].loc.z);}
#endif
  }
#endif  

#if LUDING == 1
   if (Gtime - p[a].lasttime < TheParams->cutoff || (Gtime - p[b].lasttime < TheParams->cutoff){
      rest=1.;
      alpha=0.;
      beta=2.;
   }
#endif

#if RESTTYPE == 0
  if (vsqr > (2*TheParams->g*TheParams->pdiam*1e-2)) { 
   
    
    vanf.x = 0.5 * (van.x * alpha + vbn.x * beta);
    vanf.y = 0.5 * (van.y * alpha + vbn.y * beta);
    vanf.z = 0.5 * (van.z * alpha + vbn.z * beta);
    
    vbnf.x = 0.5 * (van.x * beta + vbn.x * alpha);
    vbnf.y = 0.5 * (van.y * beta + vbn.y * alpha);
    vbnf.z = 0.5 * (van.z * beta + vbn.z * alpha); 
  }
  else
    {
      vanf.x = -van.x;
      vanf.y = -van.y;
      vanf.z = -van.z;
      vbnf.x = -vbn.x;
      vbnf.y = -vbn.y;
      vbnf.z = -vbn.z;
    }
#else if RESTTYPE == 1
    vanf.x = 0.5 * (van.x * alpha + vbn.x * beta);
    vanf.y = 0.5 * (van.y * alpha + vbn.y * beta);
    vanf.z = 0.5 * (van.z * alpha + vbn.z * beta);
    
    vbnf.x = 0.5 * (van.x * beta + vbn.x * alpha);
    vbnf.y = 0.5 * (van.y * beta + vbn.y * alpha);
    vbnf.z = 0.5 * (van.z * beta + vbn.z * alpha);
#endif  
  
  p[a].vel.x = vanf.x + vaetc.x;
  p[a].vel.y = vanf.y + vaetc.y;
  p[a].vel.z = vanf.z + vaetc.z;

  p[b].vel.x = vbnf.x + vbetc.x;
  p[b].vel.y = vbnf.y + vbetc.y;
  p[b].vel.z = vbnf.z + vbetc.z;

  if (p[a].g != p[b].g){
     p[a].g = 0;
     p[b].g = 0;
  }
  else {
     p[a].g = TheParams->g;
     p[b].g = TheParams->g;
  } 

  FE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z)+(p[b].vel.x*p[a].vel.x)+(p[b].vel.y*p[b].vel.y)+(p[b].vel.z*p[b].vel.z));
  p[a].c += 1;
  p[b].c += 1;
  BallDE+=FE-IE;
}

#else
double ballball(int a, int debug) {

  PVECTOR rabhat,vab,vt,vs,sumome,spart;
  PVECTOR dvn,dvt,newvec,dome;
  double distance,vnorm;
  double beta,betastar,opbss;  /*beta, beta^*, and (1+beta^*)^2*/
  double IE,FE;
  double RIE,RFE;
  double K=2./5.,ooK=5./2.;
  double e,factor;  
  double zmomzp,zmomyp,ymomzp,ymomyp;
  NumBallColl++;
  int amovedx,amovedy,bmovedx,bmovedy,amovedz,bmovedz;
  int zcoll;

  int b = p[a].cl->b;

/*  assert(p[a].ome.y == 0);
  assert(p[a].ome.z == 0);
  assert(p[b].ome.y == 0);
  assert(p[b].ome.z == 0);
*/


  IE=0.5*(dot(p[a].vel,p[a].vel)+dot(p[b].vel,p[b].vel));
  RIE=.05*(p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome)+p[b].diam*p[b].diam*dot(p[b].ome,p[b].ome));
 
#if FOLLOW == 1
  if (a == THIS)
   fprintf(stdout,"OH\n");
#endif

#if PERIODIC == 1 || PERIODIC == 2 || PERIODIC == 3
  amovedx=0;
  amovedy=0;
  amovedz=0;
  bmovedx=0;
  bmovedy=0;
  bmovedz=0;
#if DIMENSION == 3
  if (fabs(p[a].cell.x-p[b].cell.x) > 1)
   if (p[a].cell.x >  p[b].cell.x){
     p[a].loc.x -= XBSIZE;
     amovedx=1;
   }
   else{
     p[b].loc.x -= XBSIZE;
     bmovedx=1;
   }
#endif
  if (fabs(p[a].cell.y-p[b].cell.y) > 1)
   if (p[a].cell.y >  p[b].cell.y){
     p[a].loc.y -= YBSIZE; 
     amovedy=1;
   }
   else{
     p[b].loc.y -= YBSIZE;
     bmovedy=1;
   }
  if (fabs(p[a].cell.z-p[b].cell.z) > 1)
   if (p[a].cell.z >  p[b].cell.z){
     p[a].loc.z -= ZBSIZE; 
     amovedz=1;
   }
   else{
     p[b].loc.z -= ZBSIZE;
     bmovedz=1;
   }
#endif

  if (p[a].cell.z != p[b].cell.z){
   if (p[a].cell.z < p[b].cell.z || (p[a].cell.z == ZBSIZE && p[b].cell.z == 1) ){
      zmomzp=p[a].vel.z; 
      ymomzp=p[a].vel.y; 
   }
   else{
      zmomzp=p[b].vel.z; 
      ymomzp=p[b].vel.y; 
   }
  }

  if (p[a].cell.y != p[b].cell.y){
   if (p[a].cell.y < p[b].cell.y || (p[a].cell.y == ZBSIZE && p[b].cell.y == 1) ){
      zmomyp=p[a].vel.z; 
      ymomyp=p[a].vel.y; 
   }
   else{
      zmomyp=p[b].vel.z; 
      ymomyp=p[b].vel.y; 
   }
  }

  /*Get the unit vector pointing from a to b*/
  rabhat.x=p[b].loc.x-p[a].loc.x; 
  rabhat.y=p[b].loc.y-p[a].loc.y;
  rabhat.z=p[b].loc.z-p[a].loc.z;
  distance=sqrt(dot(rabhat,rabhat));
  rabhat.x/=distance;
  rabhat.y/=distance;
  rabhat.z/=distance;
 
  /*Get the difference in velocities*/
  vab.x=p[b].vel.x-p[a].vel.x;
  vab.y=p[b].vel.y-p[a].vel.y;
  vab.z=p[b].vel.z-p[a].vel.z;

  /*Normal velocity*/
  vnorm=dot(vab,rabhat);
//  if ((a==72 && b==120) || (a==120 && b == 72)) 
//  fprintf(stdout,"vnorm:%f\n",vnorm);
  assert(vnorm < 0.);

  vcnbar -= vnorm;

  /*Tangential velocity*/
  vt.x=vab.x-vnorm*rabhat.x;
  vt.y=vab.y-vnorm*rabhat.y; 
  vt.z=vab.z-vnorm*rabhat.z; 

  /*Get relative surface velocity*/
  sumome.x=(p[a].diam*p[a].ome.x+p[b].diam*p[b].ome.x)/2.;
  sumome.y=(p[a].diam*p[a].ome.y+p[b].diam*p[b].ome.y)/2.;
  sumome.z=(p[a].diam*p[a].ome.z+p[b].diam*p[b].ome.z)/2.;
  spart=cross(rabhat,sumome);
  vs.x=vt.x+spart.x;
  vs.y=vt.y+spart.y;
  vs.z=vt.z+spart.z;

  /*Determine beta*/
  if (dot(vs,vs) == 0)
    beta=-1;
  else{
   if (fabs(vnorm) > VMIN) 
    e = TheParams->BallRest;
   else  
    e=1-RSLOPEB*pow(fabs(vnorm),0.75);

#if LUDING == 1
   if ((Gtime - p[a].lasttime < TheParams->cutoff) || (Gtime - p[b].lasttime < TheParams->cutoff)){
      e=1.;
   }
#endif

   opbss=pow(TheParams->bmu*(1+e)*(1+ooK)*vnorm,2)/dot(vs,vs);
   if (opbss > pow(1+TheParams->beta0b,2))
     beta=TheParams->beta0b;  /*Rolling*/
   else
     beta=sqrt(opbss)-1;      /*Sliding*/
  }

#if LUDING == 1
   if ((Gtime - p[a].lasttime < TheParams->cutoff) || (Gtime - p[b].lasttime < TheParams->cutoff)){
      beta=-1.;
   }
#endif

  /*Calculate the Delta Normal Velocity*/
  factor=.5*(1+e)*vnorm;
  dvn.x=factor*rabhat.x;
  dvn.y=factor*rabhat.y;
  dvn.z=factor*rabhat.z;
  
  /*Calculate the Delta Tangential Velocity*/
  factor=K*(1+beta)/(2.*(K+1));
  dvt.x=factor*vs.x;
  dvt.y=factor*vs.y;
  dvt.z=factor*vs.z;
 
  /*Calculate the Delta omegas*/
  factor=(1+beta)/(K+1.);
  newvec=cross(rabhat,vs);
  dome.x=factor*newvec.x;
  dome.y=factor*newvec.y;
  dome.z=factor*newvec.z;

#ifdef WRITEVELS
  FILE *allvel;
  float out;
  allvel=fopen("cvs.pre","a");
  out=(float)p[a].vel.y;
  fwrite(&out,sizeof(float),1,allvel);
  out=(float)p[a].vel.z;
  fwrite(&out,sizeof(float),1,allvel);
  out=(float)p[b].vel.y;
  fwrite(&out,sizeof(float),1,allvel);
  out=(float)p[b].vel.z;
  fwrite(&out,sizeof(float),1,allvel);
  fclose(allvel);
#endif

#if PERIODIC == 3
  vc += dot(p[a].vel,p[b].vel);
#endif

  /*Update the velocites (linear and rotational)*/
  p[a].vel.x+=dvn.x+dvt.x;
  p[a].vel.y+=dvn.y+dvt.y;
  p[a].vel.z+=dvn.z+dvt.z;
  p[b].vel.x-=dvn.x+dvt.x;
  p[b].vel.y-=dvn.y+dvt.y;
  p[b].vel.z-=dvn.z+dvt.z;
  p[a].ome.x+=dome.x/p[a].diam;
  p[a].ome.y+=dome.y/p[a].diam;
  p[a].ome.z+=dome.z/p[a].diam;
  p[b].ome.x+=dome.x/p[b].diam;
  p[b].ome.y+=dome.y/p[b].diam;
  p[b].ome.z+=dome.z/p[b].diam;
  p[a].c += 1;
  p[b].c += 1;

#if PERIODIC == 3
  virial-=.5*(1+e)*vnorm*distance;
#endif
#if GK == 1
#if DIMENSION ==3
  abort();
#endif
  double dy=distance*rabhat.y;
  yz += dy*fabs(dvn.z+dvt.z);
#endif

  /*Check and make sure that particles are moving apart now.*/
  vab.x=p[b].vel.x-p[a].vel.x;
  vab.y=p[b].vel.y-p[a].vel.y;
  vab.z=p[b].vel.z-p[a].vel.z;
  vnorm=dot(vab,rabhat);
//  if ((a==72 && b==120) || (a==120 && b == 72)) 
//  fprintf(stdout,"vnorm:%f\n",vnorm);
  assert(vnorm > 0.);


  /*Calculate Energy changes*/
  FE=0.5*(dot(p[a].vel,p[a].vel)+dot(p[b].vel,p[b].vel));
  RFE=.05*(p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome)+p[b].diam*p[b].diam*dot(p[b].ome,p[b].ome));
  BallDE+=FE-IE;
  BallDRE+=RFE-RIE;

/*
  int index=(int)((e-.7)/.003);
  assert(index >= 0 && index<=100);
  balle[index][phase]+=1;
*/


#if PERIODIC ==1 || PERIODIC == 2 || PERIODIC == 3
#if DIMENSION == 3
  if (amovedx)
    p[a].loc.x+=XBSIZE;
  if (bmovedx)
    p[b].loc.x+=XBSIZE;
#endif
#if PERIODIC != 2
  if (amovedy)
    p[a].loc.y+=YBSIZE;
  if (bmovedy)
    p[b].loc.y+=YBSIZE;
#endif
#if PERIODIC == 3
  if (amovedz)
    p[a].loc.z+=ZBSIZE;
  if (bmovedz)
    p[b].loc.z+=ZBSIZE;
#endif
#endif

#if PRESSURE == 1

  if (p[a].cell.z != p[b].cell.z){
   if (p[a].cell.z < p[b].cell.z || (p[a].cell.z == ZBSIZE && p[b].cell.z == 1) ){
      zmomzp=p[a].vel.z-zmomzp; 
      ymomzp=p[a].vel.y-ymomzp; 
      pzzflux[p[a].cell.z]-=zmomzp;
      pzyflux[p[a].cell.z]-=ymomzp;
   }
   else{
      zmomzp=p[b].vel.z-zmomzp; 
      ymomzp=p[b].vel.y-ymomzp; 
      pzzflux[p[b].cell.z]-=zmomzp;
      pzyflux[p[b].cell.z]-=ymomzp;
   }
  }

  if (p[a].cell.y != p[b].cell.y){
   if (p[a].cell.y < p[b].cell.y || (p[a].cell.y == ZBSIZE && p[b].cell.y == 1) ){
      zmomyp=p[a].vel.z-zmomyp; 
      ymomyp=p[a].vel.y-ymomyp; 
      pyzflux[p[a].cell.y]-=zmomyp;
      pyyflux[p[a].cell.y]-=ymomyp;
   }
   else{
      zmomyp=p[b].vel.z-zmomyp; 
      ymomyp=p[b].vel.y-ymomyp; 
      pyzflux[p[b].cell.y]-=zmomyp;
      pyyflux[p[b].cell.y]-=ymomyp;
   }
  }



  if (fabs(p[a].cell.z - p[b].cell.z) > 3)
   zcoll=(int)(.5*(p[a].loc.z+ZBSIZE+p[b].loc.z)); 
  else
   zcoll=(int)(.5*(p[a].loc.z+p[b].loc.z)); 
  if (zcoll < 0)
    zcoll += ZBSIZE;
  if (zcoll > ZBSIZE)
    zcoll -= ZBSIZE;
  loss[zcoll]+=FE-IE;
#endif

return(IE-FE);

}

#endif


PVECTOR cross(PVECTOR a, PVECTOR b){
  PVECTOR c;
  c.x = a.y*b.z-b.y*a.z;
  c.y = b.x*a.z-a.x*b.z;
  c.z = a.x*b.y-b.x*a.y;
  return(c);
}

/*int ballballball(int a, int b, int c, int debug) {
  double uan,uat,uban,ubcn,ucn,uct;
  PVECTOR iab,icb;

  xab = p[a].loc.x-p[b].loc.x;
  yab = p[a].loc.y-p[b].loc.y;
  zab = p[a].loc.z-p[b].loc.z;
  
  xcb = p[c].loc.x-p[b].loc.x;
  ycb = p[c].loc.y-p[b].loc.y;
  zcb = p[c].loc.z-p[b].loc.z;

  magab=sqrt(xab*xab + yab*yab + zab*zab);
  magcb=sqrt(xcb*xcb + ycb*ycb + zcb*zcb);

  // A unit vector pointing from b to a;
  iab.x = xab/magab;
  iab.y = yab/magab;
  iab.z = zab/magab;

  // A unit vector pointing from b to c;
  icb.x = xcb/magcb;
  icb.y = ycb/magcb;
  icb.z = zcb/magcb;
    
  uanm = iab.x*p[a].vel.x + iab.y*p[a].vel.y + iab.z*p[a].vel.z;
  uan.x = uanm*iab.x;
  uan.y = uanm*iab.y;
  uan.z = uanm*iab.z;

  uat.x = p[a].vel.x - uan.x;
  uat.y = p[a].vel.y - uan.y;
  uat.z = p[a].vel.z - uan.z;

  ucnm = icb.x*p[c].vel.x + icb.y*p[c].vel.y + icb.z*p[c].vel.z;
  ucn.x = ucnm*icb.x;
  ucn.y = ucnm*icb.y;
  ucn.z = ucnm*icb.z;

  uct.x = p[c].vel.x - ucn.x;
  uct.y = p[c].vel.y - ucn.y;
  uct.z = p[c].vel.z - ucn.z;

  ubanm = iab.x*p[b].vel.x + iab.y*p[b].vel.y + iab.z*p[b].vel.z;

*/

void ballwall(int a, int debug, int *real) {
 int zp;
 double mag,angle;
 FILE *somebefore,*someafter;
 float tout;


/*
#if THERMAL != 1 &&  THERMAL2 != 1
if (TheParams->Ampl == 0){
   somebefore=fopen("gauss.pre","a");
   tout=(float)p[a].vel.y;
   fwrite(&tout,sizeof(float),1,somebefore);
   tout=(float)p[a].vel.z;
   fwrite(&tout,sizeof(float),1,somebefore);
   fclose(somebefore);
}
#endif
*/

#if ROTATIONS == 1
    PVECTOR van,vaetc,vanf,somome,dome;
    double vnorm,opbss,ooK=5./2.,K=2./5.;
    double RFE,factor;
#endif

  int b = p[a].cl->b;
  int temp;
  double pavtmp,pwvtmp,deltaT,rest,wdt,dt;
  double wtf;
  double RIE,IE,FE;

#if SIDESMOVE == 1
  if (p[TheParams->lwall].g > 0) 
      wdt = (Gtime-p[TheParams->lwall].time);
  else
      wdt = (Gtime-p[TheParams->lwall].time-TheParams->Period/2.);
  double wallv = TheParams->WallVel*cos(TheParams->Omega*wdt);
#endif

#if WALLFRICTION == 1
  double patmag,dvt;
  PVECTOR ut;
#endif

#if WALLFRICTION == 2
  double patmag,muw;
  PVECTOR ut;
#endif

#if ROTATIONS == 1
  double beta;
  PVECTOR rabhat,vt,vs;
#endif   

  *real=1;

  if (a == TheParams->fwall+5) {
    temp = a;
    a=b;
    b=temp;
    }

  double oldvz=p[a].vel.z;
  double oldvx=p[a].vel.x;
  double oldvy=p[a].vel.y;

#if ROTATIONS == 1
  double oldwx=p[a].ome.x;
  double oldwy=p[a].ome.y;
  double oldwz=p[a].ome.z;
#endif

#if FOLLOW == 1
  if (a == THIS){
  fprintf(stdout,"za: %f, vza: %f, ta: %f\n",p[a].loc.z,p[a].vel.z,p[a].time);
}
#endif

  if (p[b].norm.x != 0){
    evolve(a,Gtime,0);
    IE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z));

#if ROTATIONS == 1
    RIE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
#endif

    NumWallColl++;
#if RESTTYPE == 0 
    rest = TheParams->WallRest;
#else if RESTTYPE == 1
    if (fabs(p[a].vel.x) > VMIN)
      rest = TheParams->WallRest;
    else{
      rest = 1-RSLOPEW*pow(fabs(p[a].vel.x),0.75);
    }
#if LUDING == 1
    if (Gtime - p[a].time < TheParams->cutoff)
      rest = 1.;
#endif
#endif

#if ROTATIONS != 1
#if WALLFRICTION == 1

#if SIDESMOVE == 1
    p[a].vel.z -= wallv;
#endif

    patmag = sqrt(p[a].vel.y*p[a].vel.y + p[a].vel.z*p[a].vel.z);
    dvt = fabs(TheParams->wmu * p[a].vel.x);
    if (patmag > dvt){
      ut.y = p[a].vel.y/patmag*dvt;
      ut.z = p[a].vel.z/patmag*dvt;
      p[a].vel.y -= ut.y;
      p[a].vel.z -= ut.z;}
    else {
      p[a].vel.y = 0.;
      p[a].vel.z = 0.;
    }

#if SIDESMOVE == 1
    p[a].vel.z += wallv;
#endif

#endif /*WF -- 1*/

#if WALLFRICTION == 2
    patmag = sqrt(p[a].vel.y*p[a].vel.y + p[a].vel.z*p[a].vel.z);
    if (fabs(patmag) > VMIN)
      muw=TheParams->wmu;
    else
      muw = 1-RSLOPEWM*pow(fabs(patmag),0.75);
    p[a].vel.y = muw * p[a].vel.y;
    p[a].vel.z = muw * p[a].vel.z;
#endif/*WF -- 2*/

#else/*ROTATIONS*/
    rabhat.x=-1*p[b].norm.x; 
    rabhat.y=-1*p[b].norm.y; 
    rabhat.z=-1*p[b].norm.z; 

    vt.x=0;
    vt.y=-p[a].vel.y;
    vt.z=-p[a].vel.z;
    somome=cross(rabhat,p[a].ome);
    vs.x=vt.x+p[a].diam/2.*somome.x;
    vs.y=vt.y+p[a].diam/2.*somome.y;
    vs.z=vt.z+p[a].diam/2.*somome.z;
    vnorm=p[b].vel.x-p[a].vel.x;
    if (dot(vs,vs) == 0.)
      beta=-1.;
    else{
      opbss=pow(TheParams->wmu*(1+rest)*(1+ooK)*vnorm,2)/dot(vs,vs);
      if (opbss > pow((1.+TheParams->beta0w),2))
        beta=TheParams->beta0w;
      else
        beta=sqrt(opbss)-1.;
      }
    factor=(1+beta)*K/(1.+K);
    p[a].vel.y+=factor*vs.y;
    p[a].vel.z+=factor*vs.z;
    factor=2.*(1.+beta)/(p[a].diam*(1.+K)); 
    dome=cross(rabhat,vs);
    p[a].ome.y+=factor*dome.y;
    p[a].ome.z+=factor*dome.z; 
    RFE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
    WallDRE+=RFE-RIE;
#endif /*END ALL*/
    p[a].vel.x = rest * (-p[a].vel.x) + p[b].vel.x;
    FE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z));
    WallDE+=FE-IE;
  }
  

  if (p[b].norm.y != 0){
    evolve(a,Gtime,0);
    IE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z));

#if ROTATIONS == 1
    RIE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
#endif

    NumWallColl++;

#if RESTTYPE == 0 
    rest = TheParams->WallRest;
#else if RESTTYPE == 1
    if (fabs(p[a].vel.y) > VMIN)
      rest = TheParams->WallRest;
    else{
      rest = 1-RSLOPEW*pow(fabs(p[a].vel.y),0.75);
/*    Logic OK
      assert (rest <= 1.0);
      assert (rest >= TheParams->WallRest);*/
    }
#if LUDING == 1
    if (Gtime - p[a].time < TheParams->cutoff)
      rest = 1.;
#endif
#endif
#if ROTATIONS != 1
#if WALLFRICTION == 1
#if SIDESMOVE == 1
    p[a].vel.z -= wallv;
#endif
    patmag = sqrt(p[a].vel.z*p[a].vel.z + p[a].vel.x*p[a].vel.x);
    dvt = fabs(TheParams->wmu * p[a].vel.y);
    if (patmag > dvt){
      ut.z = p[a].vel.z/patmag*dvt;
      ut.x = p[a].vel.x/patmag*dvt;
      p[a].vel.z -= ut.z;
      p[a].vel.x -= ut.x;}
    else {
      p[a].vel.z = 0.;
      p[a].vel.x = 0.;
    }
#if SIDESMOVE == 1
    p[a].vel.z += wallv;
#endif
#endif
#if WALLFRICTION == 2
    patmag=sqrt(p[a].vel.z*p[a].vel.z + p[a].vel.x*p[a].vel.x); 
    if (fabs(patmag) > VMIN)
      muw=TheParams->wmu;
    else
      muw = 1-RSLOPEWM*pow(fabs(patmag),0.75);
    p[a].vel.z = muw * p[a].vel.z;
    p[a].vel.x = muw * p[a].vel.x;
#endif 
#else
    rabhat.x=-1*p[b].norm.x; 
    rabhat.y=-1*p[b].norm.y; 
    rabhat.z=-1*p[b].norm.z; 
    vt.y=0;
    vt.z=-p[a].vel.z;
    vt.x=-p[a].vel.x;
    somome=cross(rabhat,p[a].ome);
    vs.y=vt.y+p[a].diam/2.*somome.y;
    vs.z=vt.z+p[a].diam/2.*somome.z;
    vs.x=vt.x+p[a].diam/2.*somome.x;
    vnorm=p[b].vel.y-p[a].vel.y;
    if (dot(vs,vs) == 0.)
      beta=-1.;
    else{
      opbss=pow(TheParams->wmu*(1+rest)*(1+ooK)*vnorm,2)/dot(vs,vs);
      if (opbss > pow((1.+TheParams->beta0w),2))
        beta=TheParams->beta0w;
      else
        beta=sqrt(opbss)-1.;
      }
    factor=(1+beta)*K/(1.+K);
    p[a].vel.z+=factor*vs.z;
    p[a].vel.x+=factor*vs.x;
    factor=2.*(1.+beta)/(p[a].diam*(1.+K)); 
    dome=cross(rabhat,vs);
    p[a].ome.z+=factor*dome.z;
    p[a].ome.x+=factor*dome.x; 
    RFE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
    WallDRE+=RFE-RIE;
#endif
    p[a].vel.y = rest * (-p[a].vel.y) + p[b].vel.y;
    FE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z));
    WallDE+=FE-IE;
}


//  if (b == LWALL-1 && ((p[a].vel.z-p[b].vel.z)*p[b].norm.z >= 0.)){
double vtmp=p[a].vel.z-p[a].g*(Gtime-p[a].time);
  if (b == ((TheParams->lwall)-1) && ((vtmp-p[b].vel.z)*p[b].norm.z >= 0.)){
    NumWallColl++;
    evolve(a,Gtime,0);
    IE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z));

#if ROTATIONS == 1
    RIE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
#endif

#if RESTTYPE == 0 
    rest = TheParams->WallRest;
#else if RESTTYPE == 1
    if (fabs(p[a].vel.z) > VMIN)
      rest = TheParams->WallRest;
    else{
      rest = 1-RSLOPEW*pow(fabs(p[a].vel.z),0.75);
    }
#if LUDING == 1
    if (Gtime - p[a].time < TheParams->cutoff)
      rest = 1.;
#endif
#endif 

#if ROTATIONS != 1

#if WALLFRICTION == 1
    patmag = sqrt(p[a].vel.x*p[a].vel.x + p[a].vel.y*p[a].vel.y);
    dvt = fabs(TheParams->wmu * p[a].vel.z);
    if (patmag > dvt){
      ut.x = p[a].vel.x/patmag*dvt;
      ut.y = p[a].vel.y/patmag*dvt;
      p[a].vel.x -= ut.x;
      p[a].vel.y -= ut.y;}
    else {
      p[a].vel.x = 0.;
      p[a].vel.y = 0.;
    }
#endif /*WALLFRICTION == 1*/

#if WALLFRICTION == 2
    patmag=sqrt(p[a].vel.y*p[a].vel.y + p[a].vel.x*p[a].vel.x); 
    if (fabs(patmag) > VMIN)
      muw=TheParams->wmu;
    else
      muw = 1-RSLOPEWM*pow(fabs(patmag),0.75);
     p[a].vel.x = muw * p[a].vel.x;
     p[a].vel.y = muw * p[a].vel.y; 
#endif /*WALLFRICTION == 2*/

#else /*so ROTATIONS == 1*/

/* A certain way of doing thermal boundaries that doesnt really work*/
#if THERMAL2 == 1
    
  #if DIMENSION == 3  

  /*  YOU HAVEN"T WRITTEN ME YET*/

  #else SO DIM == 2

   double save=p[a].vel.y;

   
#if SLIP == 0
   p[a].vel.y = TheParams->sigt * gasdev();
#endif
if (TheParams->sigt > 0){
   p[a].vel.z = TheParams->sigt * zdev();
   if(p[a].vel.z > 0)
     p[a].vel.z *= -1;
 }
else
   p[a].vel.z *= -1;

  #endif /* DIM == 2 */


  RFE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
  WallDRE+=RFE-RIE;

#else /*so ! (THERMAL == 1)*/
/*here ends the crappy thermal boundary*/
    rabhat.x=-1*p[b].norm.x; 
    rabhat.y=-1*p[b].norm.y; 
    rabhat.z=-1*p[b].norm.z; 
    vt.z=0;
    vt.x=-p[a].vel.x;
    vt.y=-p[a].vel.y;
    somome=cross(rabhat,p[a].ome);
    vs.z=vt.z+p[a].diam/2.*somome.z;
    vs.x=vt.x+p[a].diam/2.*somome.x;
    vs.y=vt.y+p[a].diam/2.*somome.y;
    vnorm=p[b].vel.z-p[a].vel.z;
    if (dot(vs,vs) == 0.)
      beta=-1.;
    else{
      opbss=pow(TheParams->wmu*(1+rest)*(1+ooK)*vnorm,2)/dot(vs,vs);
      if (opbss > pow((1.+TheParams->beta0w),2))
        beta=TheParams->beta0w;
      else
        beta=sqrt(opbss)-1.;
      }
#if LUDING == 1
    if (Gtime - p[a].time < TheParams->cutoff)
      beta = -1.;
#endif
    factor=(1+beta)*K/(1.+K);
    p[a].vel.x+=factor*vs.x;
    p[a].vel.y+=factor*vs.y;
    factor=2.*(1.+beta)/(p[a].diam*(1.+K)); 
    dome=cross(rabhat,vs);
    p[a].ome.x+=factor*dome.x;
    p[a].ome.y+=factor*dome.y; 
    RFE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
    WallDRE+=RFE-RIE;
    p[a].vel.z = rest * (-p[a].vel.z) + p[b].vel.z;


#endif /*!(THERMAL2 == 1)*/

#endif /*ROTATIONS == 1*/

    FE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z));
    WallDE+=FE-IE;
    }
  
  if (b == LWALL){


 #if THERMAL2 == 1
    
    evolve(a,Gtime,0);
    IE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z));

#if DIMENSION == 3  
 
/*   YOU HAVEN"T WRITTEN ME YET*/

#else SO DIM == 2

/*
   somebefore=fopen("gauss.pre","a");
   tout=(float)p[a].vel.y;
   fwrite(&tout,sizeof(float),1,somebefore);
   tout=(float)p[a].vel.z;
   fwrite(&tout,sizeof(float),1,somebefore);
   fclose(somebefore);
*/

/*   angle=2*PI*drand48();
   mag = TheParams->sigb*gasdev();
   p[a].vel.y = mag * cos(angle);
   p[a].vel.z = mag * sin(angle);
   if (p[a].vel.z < 0)
    p[a].vel.z *= -1.;*/

#if SLIP == 0
   p[a].vel.y = TheParams->sigb * gasdev();
#endif
 if (TheParams->sigb > 0){
   p[a].vel.z = TheParams->sigb * zdev();
   if(p[a].vel.z < 0)
     p[a].vel.z *= -1;
 }
 else
   p[a].vel.z *= -1;

#endif DIM == 2

    NumBottColl++;
    FE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z));
    BottDE+=FE-IE;
    RFE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
    BottDRE+=RFE-RIE;

 #else so /*! (THERMAL2 == 1)*/

#ifdef GRAVDIM
  double delt1=Gtime-p[a].lgt;
  double delt2=p[a].lgt-p[a].time;
  Pvector Vo;
  Vo.x=p[a].vel.x - p[a].gvec.x * delt2;
  Vo.y=p[a].vel.y - p[a].gvec.y * delt2;
  Vo.z=p[a].vel.z - p[a].gvec.z * delt2;
  gain[p[a].cell.z-1]+=-1.*(dot(Vo,p[a].gvec)*delt1)+.5*dot(p[a].gvec,p[a].gvec)*delt1*delt1;
  p[a].lgt=Gtime;
#endif

    rabhat.x=-1*p[b].norm.x; 
    
    pavtmp = (-p[a].g * (Gtime-p[a].time)) + p[a].vel.z;
#if PLATEMOVE == 0
    pwvtmp = (-p[b].g * (Gtime-p[b].time)) + p[b].vel.z;
#else if PLATEMOVE == 1
    if (p[b].g > 0) 
	wdt = (Gtime-p[b].time);
    else
	wdt = (Gtime-p[b].time-TheParams->Period/2.);
    pwvtmp = TheParams->WallVel * cos(TheParams->Omega * wdt);
#if FOLLOW == 1
    if (a == THIS)
      fprintf(stdout,"wall velocity:%f\n",pwvtmp);
#endif
#endif
    if ((pavtmp-pwvtmp)*p[b].norm.z >= 0.){

    IE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+pavtmp*pavtmp);
#if ROTATIONS == 1
    RIE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
#endif
#if RESTTYPE == 0
      if (pwvtmp-pavtmp <=.001)
	{
	  p[a].vel.z = 2. * pwvtmp - pavtmp;
	}
      else
	p[a].vel.z = TheParams->WallRest * (-pavtmp) + (TheParams->WallRest + 1.) * pwvtmp;

#else if RESTTYPE == 1      
      if (pwvtmp - pavtmp >= VMIN)
         rest = TheParams->WallRest;
      else {
	rest = 1-RSLOPEW*pow((pwvtmp-pavtmp),0.75);
/*      Logic OK
	assert (rest <= 1.0);
	assert (rest >= TheParams->WallRest);*/
#if FOLLOW == 1
        if (a == THIS)
         fprintf(stdout,"Colliding with bottom with restitution of %f at %f\n",rest,Gtime);
#endif
      }
#if LUDING == 1
    if (Gtime - p[a].time < TheParams->cutoff)
      rest = 1.;
#endif
      
      p[a].vel.z = rest * (-pavtmp) + (rest + 1.) * pwvtmp;
#endif

/* If things really screw up: unleash the following code, and remove the line
below: p[a].loc.z = ... */

#if PLATEMOVE == 0
      p[a].loc.z = p[b].loc.z+p[a].diam/2.+(Gtime-p[b].time)*p[b].vel.z - .5 * p[b].g * (Gtime-p[b].time) * (Gtime-p[b].time);
#else if PLATEMOVE == 1
      if (p[b].g > 0)
	deltaT = Gtime - p[b].time;
      else
	deltaT = Gtime - p[b].time - TheParams->Period/2.;
      p[a].loc.z = p[b].loc.z + TheParams->Ampl * sin(TheParams->Omega * deltaT) + p[a].diam/2.;
#endif


/*      if (p[b].g > 0)
        deltaT = Gtime - p[b].time;
      else
        deltaT = Gtime - p[b].time - TheParams->Period/2.;  
  
      wtf=p[b].loc.z + TheParams->Ampl * sin(TheParams->Omega * deltaT)+ p[a].diam/2.;
*/


      dt=Gtime-p[a].time;
      p[a].loc.x += (dt)*oldvx;
      p[a].loc.y += (dt)*oldvy;
#ifdef GRAVDIM
      p[a].loc.x -= .5*p[a].gvec.x*dt*dt;
      p[a].loc.y -= .5*p[a].gvec.y*dt*dt;
      p[a].vel.x -= p[a].gvec.x * dt;
      p[a].vel.y -= p[a].gvec.y * dt;
#endif
#if  PERIODIC
#if DIMENSION == 3
  while (p[a].loc.x > XBSIZE){
    p[a].loc.x -= XBSIZE; 
    numroundx[a] += 1; }
  while (p[a].loc.x < 0){
    p[a].loc.x += XBSIZE;
    numroundx[a] -= 1; }
#endif
#if PERIODIC != 2
  while (p[a].loc.y > YBSIZE){
    p[a].loc.y -= YBSIZE; 
    numroundy[a] += 1; }
  while (p[a].loc.y < 0){
    p[a].loc.y += YBSIZE;
    numroundy[a] -= 1; }
#endif
#if PERIODIC == 3
  while (p[a].loc.z > ZBSIZE){
    p[a].loc.z -= ZBSIZE; 
    numroundz[a] += 1; }
  while (p[a].loc.z < 0){
    p[a].loc.z += ZBSIZE;
    numroundz[a] -= 1; }
#endif
#endif
//      p[a].loc.z += (dt)*oldvz - 0.5 * p[a].g * dt * dt;
#if LUDING == 1
      p[a].lasttime = p[a].time;
#endif
      p[a].time = Gtime;

#if DIMENSION == 3
  assert (p[a].loc.x < p[a].cell.x);
  assert (p[a].loc.x > (p[a].cell.x-1));
#endif
  assert (p[a].loc.y < p[a].cell.y);
  assert (p[a].loc.y > (p[a].cell.y-1));
  assert (p[a].loc.z < p[a].cell.z);
  if (p[a].loc.z <= (p[a].cell.z-1))
   fprintf(stdout,"Ballwall %i %f %i\n",a,p[a].loc.z,p[a].cell.z);
  assert (p[a].loc.z > (p[a].cell.z-1));
// fprintf(stdout,"Diff: %g\n",wtf-p[a].loc.z);

#if ROTATIONS != 1
#if WALLFRICTION == 1
    patmag = sqrt(p[a].vel.x*p[a].vel.x + p[a].vel.y*p[a].vel.y);
    dvt = fabs(TheParams->wmu * (pavtmp-pwvtmp));
    if (patmag > dvt){
      ut.x = p[a].vel.x/patmag*dvt;
      ut.y = p[a].vel.y/patmag*dvt;
      p[a].vel.x -= ut.x;
      p[a].vel.y -= ut.y;}
    else {
      p[a].vel.x = 0.;
      p[a].vel.y = 0.;
    }
#endif
#if WALLFRICTION == 2 
    patmag=sqrt(p[a].vel.y*p[a].vel.y + p[a].vel.x*p[a].vel.x); 
    if (fabs(patmag) > VMIN)
      muw=TheParams->wmu;
    else
      muw = 1-RSLOPEWM*pow(fabs(patmag),0.75);
    p[a].vel.x = muw * p[a].vel.x;
    p[a].vel.y = muw * p[a].vel.y;
#endif
#else
    rabhat.x=-1*p[b].norm.x; 
    rabhat.y=-1*p[b].norm.y; 
    rabhat.z=-1*p[b].norm.z; 
    vt.z=0;
    vt.x=-p[a].vel.x;
    vt.y=-p[a].vel.y;
    somome=cross(rabhat,p[a].ome);
    vs.z=vt.z+p[a].diam/2.*somome.z;
    vs.x=vt.x+p[a].diam/2.*somome.x;
    vs.y=vt.y+p[a].diam/2.*somome.y;
    vnorm=pwvtmp-pavtmp;
    if (dot(vs,vs) == 0.)
      beta=-1.;
    else{
      opbss=pow(TheParams->wmu*(1+rest)*(1+ooK)*vnorm,2)/dot(vs,vs);
      if (opbss > pow((1.+TheParams->beta0w),2))
        beta=TheParams->beta0w;
      else
        beta=sqrt(opbss)-1.;
      }
    factor=(1+beta)*K/(1.+K);
    p[a].vel.x+=factor*vs.x;
    p[a].vel.y+=factor*vs.y;
    factor=2.*(1.+beta)/(p[a].diam*(1.+K)); 
    dome=cross(rabhat,vs);
    p[a].ome.x+=factor*dome.x;
    p[a].ome.y+=factor*dome.y; 
    RFE=.05*p[a].diam*p[a].diam*dot(p[a].ome,p[a].ome);
    BottDRE+=RFE-RIE;
#endif

#if FOLLOW == 1
      if (a == THIS)
	fprintf(stdout,"New particle velocity:%f\n",p[a].vel.z);
#endif
    NumBottColl++;
    FE=0.5*((p[a].vel.x*p[a].vel.x)+(p[a].vel.y*p[a].vel.y)+(p[a].vel.z*p[a].vel.z));
    BottDE+=FE-IE;
    int index=(int)((rest-0.7)/0.003);
    assert(index >=0 && index <=100);
    walle[index][phase]+=1;

/*#if DIMENSION == 3
    if (p[a].loc.x < rightp)
     if (p[a].loc.y < backp) 
      if (p[a].loc.x > leftp)
       if (p[a].loc.y > frontp)
         if (pow(p[a].loc.x-midpx,2)+pow(p[a].loc.y-midpy,2) < radp*radp)
#endif*/
           impulse += (p[a].vel.z - pavtmp);
    }

    else{
      *real = 0;
#if FOLLOW == 1
      if (a == THIS){
	fprintf(stdout,"bottom Bogus collision ignored!\n");
	fprintf(stdout,"wallvelocity: %f, ball velocity:%f\n",pwvtmp,pavtmp);}
#endif
     }

#endif /*!(THERMAL2 == 1)*/


  }


  if (*real != 0){
    p[a].wallcalc += 1;
    p[a].c += 1;
  }

/*  assert(p[a].ome.y == 0);
  assert(p[a].ome.z == 0);
  assert(p[b].ome.y == 0);
  assert(p[b].ome.z == 0);
*/
/*
#if THERMAL != 1 &&  THERMAL2 != 1
   someafter=fopen("gauss.post","a");
   tout=(float)p[a].vel.y;
   fwrite(&tout,sizeof(float),1,someafter);
   tout=(float)p[a].vel.z;
   fwrite(&tout,sizeof(float),1,someafter);
   fclose(someafter);
#endif
*/

}

void statstat(int a) {
  static float countf=0.;
  static int firsttime = 2;
  int i,j,NumNeighbors,x,y,z,old;
  double bodyvirial = 0.0;
  double SysKE = 0.0;
  double SysPE = 0.0; 
  double AvgVz = 0.0;
  double AvgVx = 0.0;
  double AvgVy = 0.0;
  double AvgVz2 = 0.0;
  double AvgVy2 = 0.0;
  double AvgVx2 = 0.0;
  double escapees = 0.0;
  double newpos;
#if PERIODIC ==1 || PERIODIC == 2 || PERIODIC == 3
  double Var = 0.0;
#endif
#if QFLOATS == 0 
#if DIMENSION != 1
  float out[26];
#else
  float out[10];
#endif
  float tempx1,tempy1,tempz1,tempvx1,tempvy1,tempvz1,wtempz1;
#if ROTATIONS == 1
  float tempwx1,tempwy1,tempwz1,tempvw1;
#endif
#ifdef GRAVDIM 
  float tempgx,tempgy,tempgz;
#endif
#else  
  double out[26];
#endif
#if PLATEMOVE == 1
  double sign,dt;
#endif
  double deltaT,wtempz,wtempvz,tempx,tempy,tempz,tempvx,tempvy,tempvz;
  double compact = 0.0;
//#if ROTATIONS == 1
  double SysRE=0.,AvgWz=0.,AvgWy=0.,AvgWx=0.,AvgWz2=0.,AvgWx2=0.,AvgWy2=0.;
  double tempwx,tempwy,tempwz;
//#endif
//  double minz[5],maxz[5];

#ifdef CRUNCHER
  double minz=1000.;
#endif
  

  p[a].time = Gtime;
  
  if (a == TheParams->fstat) {
   
   char name[50]; 
   phase+=1;
   if (phase == 100)
    phase=0;
   FILE *ballefile,*wallefile,*fluxfile,*vzfile,*lossfile,*gainfile;
   #if GK==1
   FILE *kubo;
   strcpy(name,RUN);
   strcat(name,".gk");
   kubo=fopen(name,"wa");
   #endif

#ifdef GETBE
   strcpy(name,RUN);
   strcat(name,".be");
   ballefile=fopen(name,"wb");
   strcpy(name,RUN);
   strcat(name,".we");
   wallefile=fopen(name,"wb");
#endif

#if PRESSURE == 1

   strcpy(name,RUN);
   strcat(name,".pflux");
   fluxfile=fopen(name,"w");
   strcpy(name,RUN);
   strcat(name,".vzbar");
   vzfile=fopen(name,"w");
   strcpy(name,RUN);
   strcat(name,".loss");
   lossfile=fopen(name,"w");
   strcpy(name,RUN);
   strcat(name,".gain");
   gainfile=fopen(name,"w");

#endif

   /*walle and balle are written out each time stats are written.  */
   /*When read into IDL using loa(), the order is (phase,e), each */
   /*increasing with the index*/

#ifdef GETBE
   fwrite(balle,sizeof(balle[0][0]),10100,ballefile);
   fwrite(walle,sizeof(balle[0][0]),10100,wallefile);
#endif
#if PRESSURE == 1
   fwrite(pyyflux,sizeof(pzzflux[0]),ZGSIZE,fluxfile);
   fwrite(pyzflux,sizeof(pzzflux[0]),ZGSIZE,fluxfile);
   fwrite(pzyflux,sizeof(pzzflux[0]),ZGSIZE,fluxfile);
   fwrite(pzzflux,sizeof(pzzflux[0]),ZGSIZE,fluxfile);
   fwrite(vzbar,sizeof(vzbar[0]),ZGSIZE,vzfile);
   fwrite(loss,sizeof(vzbar[0]),ZBSIZE,lossfile);
   fwrite(gain,sizeof(vzbar[0]),ZBSIZE,gainfile);
#endif

#ifdef GETBE
   fclose(ballefile);
   fclose(wallefile);
#endif
#if PRESSURE == 1
   fclose(fluxfile);
   fclose(vzfile);
   fclose(lossfile);
   fclose(gainfile);

#endif


   open_stats();

/*  fprintf(stdout,"Going to do stats now, Gtime=%f\n",Gtime);*/

//    clocker= ((double)clock())/CLOCKS_PER_SEC - clocker;
    
/*    for (i=0;i<5;i++){
      maxz[i]=(1.*i - 100.);
      minz[i]=1.*(1000+i);}*/
    
    escapees=0;
    deltaT = Gtime - p[TheParams->fwall+5].time;
#if PLATEMOVE == 0 || PLATEMOVE == -1
    wtempz = p[TheParams->fwall+5].loc.z + p[TheParams->fwall+5].vel.z * deltaT - .5 * p[TheParams->fwall+5].g * deltaT * deltaT; 
#else if PLATEMOVE == 1
    sign=copysign(1.,p[TheParams->lwall].g);
    wtempz = p[TheParams->fwall+5].loc.z + TheParams->Ampl*sin(TheParams->Omega*deltaT)*sign;
#if FOLLOW == 1
    fprintf(stdout,"\nPlate Position:%f\n",wtempz);
#endif
#endif

  double gtoty=0,gtotz=0;

    for(i=TheParams->fball;i<=TheParams->lball;++i) {
      deltaT = Gtime - p[i].time;
#if PERIODIC == 1 || PERIODIC == 2 || PERIODIC == 3
      tempy = p[i].loc.y + p[i].vel.y * deltaT;
      tempx = p[i].loc.x + p[i].vel.x * deltaT;
      tempz = p[i].loc.z + p[i].vel.z * deltaT - .5*p[i].g*deltaT*deltaT;
#ifdef CRUNCHER
      if (tempz<minz)
        minz=tempz;
#endif
#if DIMENSION == 3
      Var += pow((tempx+XBSIZE*numroundx[i]-startx[i]),2); 
#endif /*DIM == 3*/
#if PERIODIC != 2
      Var += pow((tempy+YBSIZE*numroundy[i]-starty[i]),2); 
#endif
#if PERIODIC == 3
      Var += pow((tempz+ZBSIZE*numroundz[i]-startz[i]),2);
#endif
#endif/*PERIODIC*/

     
      tempz = p[i].loc.z + p[i].vel.z * deltaT - 0.5 * p[i].g * deltaT * deltaT;
      tempvz = p[i].vel.z - p[i].g * deltaT;
      tempvx = p[i].vel.x;
      tempvy = p[i].vel.y;

#ifdef GRAVDIM
      tempx = p[i].loc.x + p[i].vel.x * deltaT - 0.5 * //
         p[i].gvec.x * deltaT * deltaT;
      tempvx = p[i].vel.x - p[i].gvec.x * deltaT;
      tempy = p[i].loc.y + p[i].vel.y * deltaT - //
         0.5 * p[i].gvec.y * deltaT * deltaT;
      tempvy = p[i].vel.y - p[i].gvec.y * deltaT;
      gtoty += p[i].gvec.y;
      gtotz += p[i].gvec.z;
      if (tempx < 0)
       tempx+=XBSIZE;
      if (tempx > XBSIZE )
       tempx-=XBSIZE;
      if (tempy < 0)
       tempy+=YBSIZE;
      if (tempy > YBSIZE )
       tempy-=YBSIZE;
      if (tempz < 0)
       tempz+=ZBSIZE;
      if (tempz > ZBSIZE )
       tempz-=ZBSIZE;
      bodyvirial -= tempx*p[i].gvec.x + tempy*p[i].gvec.y + tempz*p[i].gvec.z;
#endif

      SysKE = SysKE + 0.5 * (tempvx*tempvx + tempvy * tempvy + tempvz * tempvz);
      SysPE = SysPE + tempz - p[TheParams->lwall].loc.z; 
#if ROTATIONS == 1
      SysRE = SysRE + 0.05*p[i].diam*p[i].diam*dot(p[i].ome,p[i].ome);
#endif
      AvgVz = AvgVz + tempvz;
      AvgVx = AvgVx + tempvx;
      AvgVy = AvgVy + tempvy;
      AvgVz2= AvgVz2 + tempvz*tempvz;
      AvgVy2= AvgVy2 + tempvy * tempvy;
      AvgVx2= AvgVx2 + tempvx * tempvx;
#if ROTATIONS == 1
      AvgWz = AvgWz + p[i].ome.z;
      AvgWy = AvgWy + p[i].ome.y;
      AvgWx = AvgWx + p[i].ome.x;
      AvgWz2 = AvgWz2 + p[i].ome.z*p[i].ome.z;
      AvgWy2 = AvgWy2 + p[i].ome.y*p[i].ome.y;
      AvgWx2 = AvgWx2 + p[i].ome.x*p[i].ome.x;
#endif

      
#if PERIODIC != 3
      if (tempz < wtempz) {
         fprintf(stdout,"Particle Escape, ball: %d,  Gtime=%f\n",i,Gtime);
	 fprintf(stdout,"Ball position: %f, Wall position: %f \n",tempz,wtempz);
         escapees += 1.; 
         bomb(9,i);
      }
#endif
    }
 
    AvgVz = AvgVz/(1.*NMOV);
    AvgVx /= (1.*NMOV);
    AvgVy /= (1.*NMOV);
    AvgVy2 /= (1.*NMOV);
    AvgVx2 /= (1.*NMOV);
    AvgVz2 /= (1.*NMOV);
    SysKE = SysKE/(1.*NMOV);
    //fprintf(stdout,"SYSKE=%f\n",SysKE);
    SysPE = SysPE/(1.*NMOV); 
#if ROTATIONS == 1
    SysRE = SysRE/(1.*NMOV);
    AvgWx /= (1.*NMOV);
    AvgWy /= (1.*NMOV);
    AvgWz /= (1.*NMOV);
    AvgWx2 /= (1.*NMOV);
    AvgWy2 /= (1.*NMOV);
    AvgWz2 /= (1.*NMOV);
#endif
#if PERIODIC
    Var /= (1.*NMOV);
#endif
/*    for (j=0;j<5;j++)
      compact=compact+maxz[j]-minz[j];*/
//    fprintf(stdout,"compact=%g\n",compact);
#if QFLOAT != 0
    out[0]=SysKE;
    out[1]=SysPE;
    out[2]=SysRE;
    out[3]=AvgVx;
    out[4]=AvgVy;
    out[5]=AvgVz;
    out[6]=AvgVx2;
    out[7]=AvgVy2;
    out[8]=AvgVz2;
#if ROTATIONS == 1
    out[9]=AvgWx;
    out[10]=AvgWy;
    out[11]=AvgWz;
    out[12]=AvgWx2;
    out[13]=AvgWy2;
    out[14]=AvgWz2;
#else
    out[9]=0.;
    out[10]=0.;
    out[11]=0.;
    out[12]=0.;
    out[13]=0.;
    out[14]=0.;
#endif
    out[15]=NumBallColl;
    out[16]=NumWallColl;
    out[17]=NumBottColl;
    out[18]=BallDE;
    out[19]=WallDE;
    out[20]=BottDE;
#if ROTATIONS == 1
    out[21]=BallDRE;
    out[23]=BottDRE;
    out[22]=WallDRE;
#else
    out[21]=0.;
    out[23]=0.;
    out[22]=0.;
#endif
    out[24]=wtempz;
    out[24]=impulse;
#else
#if DIMENSION != 1
    out[0]=(float)SysKE;
    out[1]=(float)SysPE;
    out[2]=(float)SysRE;
    out[3]=(float)AvgVx;
    out[4]=(float)AvgVy;
    out[5]=(float)AvgVz;
    out[6]=(float)AvgVx2;
    out[7]=(float)AvgVy2;
    out[8]=(float)AvgVz2;
 #if ROTATIONS==1
    out[9]=(float)AvgWx;
    out[10]=(float)AvgWy;
    out[11]=(float)AvgWz;
    out[12]=(float)AvgWx2;
    out[13]=(float)AvgWy2;
    out[14]=(float)AvgWz2;
   #ifdef GRAVDIM
    out[9]=(float)gtoty; 
    out[10]=(float)gtotz; 
    out[11]=(float)bodyvirial; 
   #endif
  #else
    out[9]=0.;
    out[10]=0.;
    out[11]=0.;
    out[12]=0.;
    out[13]=0.;
    out[14]=0.;
 #endif
    out[15]=(float)NumBallColl;
    //fprintf(stdout,"Number of Colls between Balls: %f\n",out[15]);
    out[16]=(float)NumWallColl;
    out[17]=(float)NumBottColl;
    //fprintf(stdout,"Number of Colls with Bottom: %f\n",out[17]);
    out[18]=(float)BallDE;
    out[19]=(float)WallDE;
    out[20]=(float)BottDE;
 #if ROTATIONS == 1
    out[21]=(float)BallDRE;
    out[23]=(float)BottDRE;
    out[22]=(float)WallDRE;
 #else
    out[21]=0.;
    out[23]=0.;
    out[22]=0.;
 #endif
#if PERIODIC
    out[24]=(float)Var;
#endif
#if PERIODIC == 3
    out[24]=(float)(vcnbar/NumBallColl);
    out[25]=(float)virial;
#else
    out[25]=(float)impulse;
#endif
#else
    out[0]=(float)SysKE;
    out[1]=(float)SysPE;
    out[2]=(float)AvgVx;
    out[3]=(float)AvgVx2;
    out[4]=(float)NumBallColl;
    out[5]=(float)NumBottColl;
    out[6]=(float)BallDE;
    out[7]=(float)BottDE;
    out[8]=(float)wtempz;
    out[9]=(float)impulse;
#endif
#endif
    fwrite(out,sizeof(out),1,stats);
    NumBallColl=0;
    NumWallColl=0;
    NumBottColl=0;
    BallDE=0;
    WallDE=0;
    BottDE=0;
    vcnbar=0;
#if ROTATIONS == 1
    BallDRE=0.;
    WallDRE=0.;
    BottDRE=0.;
#endif
    impulse=0;

    float xs[10];
  
    for (i=0;i<10;i++){
       j=i*(int)(1.*NMOV/10.);
       xs[i]=(float)(p[j].loc.y+p[j].vel.y*(Gtime-p[j].time));
    }

    fwrite(xs,sizeof(xs),1,tracks);

//    fprintf(stdout,"Stats Written at Gtime = %f\n",Gtime);
   close_stats();

#if GK == 1

  double kout[3];

  double sumvc=0.;
  double vyvz=0.;
  double excess=0.;
  double Szt1=0.,Syt1=0.;
  for (i=0;i<TheParams->nball;i++) {
    sumvc += dot(p[i].vel,vinit[i]);
    vyvz += p[i].vel.y*p[i].vel.z; 
    excess = .5*dot(p[i].vel,p[i].vel)-AvgKE;
    Syt1+=excess*p[i].vel.y;
    Szt1+=excess*p[i].vel.z;
  }
  sumvc /= (1.*TheParams->nball*DIMENSION);
  D+=sumvc*TimeStep;
  kout[0]=D;

  double avgyz=yz/TimeStep;
  double Pyz = vyvz + avgyz;
  if (firsttime){
    firsttime--;  
    Pyz0=Pyz;
    kout[1]=0;
  }
  else{
    eta += Pyz*Pyz0*TimeStep/(1.*DIMENSION)/AvgKE;
    kout[1]=eta;
  }
  yz=0.;
  
  

  fwrite(kout,sizeof(kout),1,kubo);
  fclose(kubo);
#endif

#ifdef CRUNCHER

  double newpos=minz-p[0].diam/2.-.0001;
   if (newpos > p[TheParams->lwall].loc.z){
     p[TheParams->lwall].loc.z=newpos;
     for (i=0;i<26;i++){
      lel_destroy(i,0);  
      c_calc(i,0);
      fel_resort(i);
     }
     fprintf(stdout,"Moved the bottom to %f at %f\n",newpos,Gtime);
   }
  

#endif

  }
  
  if (a == TheParams->fstat + 1 && TheParams->Ampl !=0.) {


/* The case of the kick:
   for(i=TheParams->fball;i<=TheParams->lball;i++) {
      newpos = p[i].loc.z + TheParams->Ampl * TheParams->pdiam;
      if (newpos < BSIZE){
        if (newpos > p[i].cell.z){
          p[i].cell.z += 1;
          TheGrid[p[i].cell.x][p[i].cell.y][p[i].cell.z].remove(a);
          TheGrid[p[i].cell.x][p[i].cell.y][p[i].cell.z+1].add(a);
         } 
      	p[i].loc.z = newpos;
      }
      }

      lel_destroy_all();
      cl_calc(0);
      fel_sort(0);*/
    
    /* The case of the triangle bottom: To END TRIANGLE*/
    
    /*If we were at the bottom coming up:  We have to set the right position
     for the plate, the balls, reset the balls g's, and recalculate their
     collisions, although not until everybody's g has been set.*/
/*    if (p[TheParams->fwall+5].loc.z == WOFFSET){
      p[TheParams->fwall+5].loc.z = WOFFSET + 2*TheParams->Ampl;
      for (x=1;x<=BSIZE;x++){
	for (y=1;y<=BSIZE;y++){
         for (z=1;z<=BSIZE;z++){
	  NumNeighbors=TheGrid[x][y][z].members(TheNeighbors);
	  for (i=0;i<NumNeighbors;i++){
	    if (p[TheNeighbors[i]].g == 0){
	      p[TheNeighbors[i]].c += 1;
              evolve(TheNeighbors[i],Gtime,0);
	      p[TheNeighbors[i]].g = TheParams->g;
	      lel_destroy(TheNeighbors[i],0);
//	      printf("%i Unstick, p.z=%f, p.v.z=%f, w.z=%f w.v.z=%f\n",p[TheNeig//hbors[i]].loc.z,p[TheNeighbors[i]].vel.z,p[TheParams->fwall+5].loc.z,p[ThePara//ms->fwall+5].vel.z);
	     } 
            }
	  }
	}
	}
      for (x=1;x<=BSIZE;x++){
	for (y=1;y<=BSIZE;y++){
	  NumNeighbors=TheGrid[x][y][1].members(TheNeighbors);
	  for (i=0;i<NumNeighbors;i++){
	    if (p[TheNeighbors[i]].cl == NULL)
	      c_calc(TheNeighbors[i],0);
	  }
	}
      }
    }  */
    /* If we are going down, We still give the plate its correct postion, and
       recalculate collisions for the balls, but instead of turning on the
       particles' gravity, we switch the sign of their velocities.*/
/*    else{
      p[TheParams->fwall+5].loc.z = WOFFSET;
      for (x=1;x<=BSIZE;x++){
	for (y=1;y<=BSIZE;y++){
	  NumNeighbors=TheGrid[x][y][1].members(TheNeighbors);
	  for (i=0;i<NumNeighbors;i++){
//	    printf("?? TheNeigbors[i]=%i, g=%f\n",TheNeighbors[i],p[TheNeighbors//[i]].g);
	    if (p[TheNeighbors[i]].g == 0){
	      p[TheNeighbors[i]].c += 1;
              evolve(TheNeighbors[i],Gtime,0);
	      p[TheNeighbors[i]].vel.z = -p[TheNeighbors[i]].vel.z;
//	      printf("Turnaround: %i\n",TheNeighbors[i]);
	    }
	  }
	}
      }
      for (x=1;x<=BSIZE;x++){
	for (y=1;y<=BSIZE;y++){
	  NumNeighbors=TheGrid[x][y][1].members(TheNeighbors);
	  for (i=0;i<NumNeighbors;i++){
	    if (p[TheNeighbors[i]].g == 0){
	      lel_destroy(TheNeighbors[i],0);
	      c_calc(TheNeighbors[i],0);
	    }
	  }
	  }
	  }
	  }
 */   
    /*By waiting until after the balls are covered before rebuilding the 
      collision list for the plate, we should avoid misses & double collisions
      &c. */
/*    p[TheParams->fwall+5].vel.z = -p[TheParams->fwall+5].vel.z;
    p[TheParams->fwall+5].c +=1; 
    p[TheParams->fwall+5].time = Gtime;
    lel_destroy(TheParams->fwall+5,0);
    cw_calc(0);
*/
/* END TRIANGLE */

/* START PARABOLIC*/
    /*If we were on the lower half of the cycle: reverse the velocity and
     acceleration for the plate, recalculate its collisions, and set anybody
     whose g is wall.g to regular g. If somebody gets his g reset, recalculate 
     his collision list. This is the plate.g < 0, since we have the
     eqn of motion z = zo +vot - pg/2 * t^2  .  Note the - sign.*/
    if (p[TheParams->fwall+5].g < 0.){
#if GAMMASWEEP == 1
      if (period_count == GAMMATIME) {
      p[TheParams->fwall+5].g = -p[TheParams->fwall+5].g + GAMMASTEP; 
#if PLATEMOVE == 0
      p[TheParams->fwall+5].vel.z = p[TheParams->fwall+5].g * TheParams->Period/4.;
#else if PLATEMOVE == 1
      TheParams->Ampl = p[TheParams->fwall+5].g/TheParams->Omega/TheParams->Omega;
      TheParams->WallVel = TheParams->Ampl * TheParams->Omega;
      TheParams->TimeOne = (asin(1./p[TheParams->fwall+5].g)/TheParams->Omega);
      fprintf(stdout,"New Amplitude:%f\t\tNew Velocity:%f\n",TheParams->Ampl,TheParams->WallVel);
      fprintf(stdout,"New TimeOne:%f\n",TheParams->TimeOne);
#endif
      fprintf(stdout,"Changed GAMMA to %f at Gtime = %f\n",p[TheParams->fwall+5].g,Gtime);
      period_count = 1;}
      else {
      period_count += 1;
#endif
      p[TheParams->fwall+5].g = -p[TheParams->fwall+5].g;
      p[TheParams->fwall+5].vel.z = -p[TheParams->fwall+5].vel.z;
#if GAMMASWEEP == 1
      }
#endif
/*      for (x=1;x<=XBSIZE;x++){
	for (y=1;y<=YBSIZE;y++){
         for (z=1;z<=ZBSIZE;z++){
	  NumNeighbors=TheGrid[x][y][z].members(TheNeighbors);
	  for (i=0;i<NumNeighbors;i++){
	    if (p[TheNeighbors[i]].g == -p[TheParams->fwall+5].g){
	      p[TheNeighbors[i]].c += 1;
              evolve(TheNeighbors[i],Gtime,0);
	      p[TheNeighbors[i]].g = TheParams->g;
	      lel_destroy(TheNeighbors[i],0);
//	      printf("%i Unstick, p.z=%f, p.v.z=%f, w.z=%f w.v.z=%f\n",p[TheNeig//hbors[i]].loc.z,p[TheNeighbors[i]].vel.z,p[TheParams->fwall+5].loc.z,p[ThePara//ms->fwall+5].vel.z);
	     } 
	  }
	}
       }
       }*/
      for (x=1;x<=XBSIZE;x++){
	for (y=1;y<=YBSIZE;y++){
	  NumNeighbors=TheGrid[x][y][1].members(TheNeighbors);
	  for (i=0;i<NumNeighbors;i++){
	    if (p[TheNeighbors[i]].cl == NULL)
	      c_calc(TheNeighbors[i],0);
	  }
	}
	}
      }
    
    /*Now, if the plate is in the top half of the cycle, flip its velocity and
      acceleration. If anybody is stuck to the plate, update them, reverse 
      their gravity, and recalc their list*/
     else{
      p[TheParams->fwall+5].vel.z = -p[TheParams->fwall+5].vel.z;
      p[TheParams->fwall+5].g = -p[TheParams->fwall+5].g;
      for (x=1;x<=XBSIZE;x++){
	for (y=1;y<=YBSIZE;y++){
	  NumNeighbors=TheGrid[x][y][1].members(TheNeighbors);
	  for (i=0;i<NumNeighbors;i++){
//	    printf("?? TheNeigbors[i]=%i, g=%f\n",TheNeighbors[i],p[TheNeighbors//[i]].g);
	    if (p[TheNeighbors[i]].g == -p[TheParams->fwall+5].g){
	      p[TheNeighbors[i]].c += 1;
              evolve(TheNeighbors[i],Gtime,0);
	      p[TheNeighbors[i]].g = -p[TheNeighbors[i]].g;
//	      printf("Turnaround: %i\n",TheNeighbors[i]);
	    }
	  }
	}
      }
      for (x=1;x<=XBSIZE;x++){
	for (y=1;y<=YBSIZE;y++){
	  NumNeighbors=TheGrid[x][y][1].members(TheNeighbors);
	  for (i=0;i<NumNeighbors;i++){
	    if (p[TheNeighbors[i]].g == p[TheParams->fwall+5].g){
	      lel_destroy(TheNeighbors[i],0);
	      c_calc(TheNeighbors[i],0);
	    }
	  }
	}
      }
    }
    /*By waiting until after the balls are covered before rebuilding the 
      collision list for the plate, we should avoid misses & double collisions
      &c. */
//    p[TheParams->fwall+5].vel.z = -p[TheParams->fwall+5].vel.z;
    p[TheParams->fwall+5].c +=1; 
    p[TheParams->fwall+5].time = Gtime;
    lel_destroy(TheParams->fwall+5,0);
    cw_calc(0);
    fel_resort(TheParams->fwall+5);
  }
 
  if (a==TheParams->fstat+2) {

  open_files();

   double ntempx,ntempy,ntempz;
    for (i=TheParams->fball;i<=TheParams->lball;i++){
      deltaT = Gtime - p[i].time;
      tempx=p[i].loc.x + p[i].vel.x * deltaT;
      tempy=p[i].loc.y + p[i].vel.y * deltaT;
      tempz=p[i].loc.z + p[i].vel.z * deltaT - .5 * p[i].g * deltaT * deltaT;
#ifdef GRAVDIM
      tempx -= .5*p[i].gvec.x * deltaT * deltaT;
      tempy -= .5*p[i].gvec.y * deltaT * deltaT;
#endif
#if PERIODIC
     ntempx=tempx;
     ntempy=tempy;
     ntempz=tempz;
#if DIMENSION == 3
     while (ntempx > XBSIZE)
      ntempx-=XBSIZE; 
     while (ntempx < 0)
      ntempx+=XBSIZE; 
#endif
#if PERIODIC != 2
     while (ntempy > YBSIZE)
      ntempy-=YBSIZE; 
     while (ntempy < 0)
      ntempy+=YBSIZE; 
#endif
#if PERIODIC == 3
     while (ntempz > ZBSIZE)
      ntempz-=ZBSIZE; 
     while (ntempz < 0)
      ntempz+=ZBSIZE; 
#endif
#if DIMENSION == 3
  assert (ntempx < p[i].cell.x);
  assert (ntempx > (p[i].cell.x-1));
#endif
#if PERIODIC != 2
 if (ntempy > p[i].cell.y){
  assert (ntempy < p[i].cell.y);
 }
  assert (ntempy> (p[i].cell.y-1));
#endif
#if PERIODIC == 3
  assert (ntempz < p[i].cell.z);
  assert (ntempz> (p[i].cell.z-1));
#endif
#endif
      tempvx=p[i].vel.x;
      tempvy=p[i].vel.y;
      tempvz=p[i].vel.z - p[i].g * deltaT;
#ifdef GRAVDIM
      tempvx -= p[i].gvec.x * deltaT;
      tempvy -= p[i].gvec.y * deltaT;
#endif
#if ROTATIONS == 1
      tempwx=p[i].ome.x;
      tempwy=p[i].ome.y;
      tempwz=p[i].ome.z;
#endif
#if QFLOATS != 0
#if DIMENSION == 3
      fwrite(&tempx,sizeof(p[i].loc.x),1,pos);
#endif /*DIMENSIONS == 3*/
#if DIMENSION != 1
      fwrite(&tempy,sizeof(p[i].loc.x),1,pos);
#endif /*DIM != 1*/
      fwrite(&tempz,sizeof(p[i].loc.x),1,pos);
#if DIMENSION == 3
      fwrite(&tempvx,sizeof(p[i].loc.x),1,vel);
#endif /*DIM != 3*/
#if DIMENSION != 1
      fwrite(&tempvy,sizeof(p[i].loc.x),1,vel);
#endif /*DIM != 1*/
      fwrite(&tempvz,sizeof(p[i].loc.x),1,vel); }
#else /* Now, QFLOATS == 0 -- this is the one we use*/
      tempx1=(float)tempx;
      tempy1=(float)tempy;
      tempz1=(float)tempz;
      tempvx1=(float)tempvx;
      tempvy1=(float)tempvy;
      tempvz1=(float)tempvz;
#if ROTATIONS == 1
      tempwx1=(float)p[i].ome.x;
      tempwy1=(float)p[i].ome.y;
      tempwz1=(float)p[i].ome.z;
#endif/*ROT == 1*/
#ifdef GRAVDIM
      tempgx=(float)p[i].gvec.x;
      tempgy=(float)p[i].gvec.y;
      tempgz=(float)p[i].gvec.z;
#endif

#if DIMENSION == 3
      fwrite(&tempx1,sizeof(tempx1),1,pos);
#endif /* DIM == 3*/
#if DIMENSION != 1
      fwrite(&tempy1,sizeof(tempy1),1,pos);
#endif /* DIM == 1 */
      fwrite(&tempz1,sizeof(tempz1),1,pos);

#if DIMENSION ==3
      fwrite(&tempvx1,sizeof(tempvx1),1,vel);
#endif /*DIM == 3*/
#if DIMENSION != 1
      fwrite(&tempvy1,sizeof(tempvy1),1,vel);
#endif /*DIM !=1*/
      fwrite(&tempvz1,sizeof(tempvz1),1,vel);

#if ROTATIONS == 1
      fwrite(&tempwx1,sizeof(tempvx1),1,ome);
#if DIMENSION ==3
      fwrite(&tempwy1,sizeof(tempvw1),1,ome);
      fwrite(&tempwz1,sizeof(tempvw1),1,ome);
#endif /*DIM == 3*/
#endif /*ROT == 1*/

#ifdef GRAVDIM 
#if DIMENSION ==3
      fwrite(&tempgx,sizeof(tempvx1),1,gs);
#endif /*DIM == 3*/
      fwrite(&tempgy,sizeof(tempvw1),1,gs);
      fwrite(&tempgz,sizeof(tempvw1),1,gs);
#endif /*ROT == 1*/


#if COUNTCOLS == 1
  fwrite(&p[i].c,sizeof(p[i].c),1,numcoll);
/*  fwrite(&p[i].wallcalc,sizeof(p[i].c),1,numcoll);
  p[i].wallcalc = 0;*/
#endif /*Countcols == 1*/

#if PERIODIC
#if DIMENSION == 3
    fwrite(&numroundx[i],sizeof(&numroundx[i]),1,crossings);
#endif /*DIMENSION == 3*/
#if PERIODIC != 2
    fwrite(&numroundy[i],sizeof(&numroundy[i]),1,crossings);
#endif
#if PERIODIC == 3
    fwrite(&numroundz[i],sizeof(&numroundz[i]),1,crossings);
#endif
#endif /*PERIODIC1*/
     }
#endif /*QFLOAT == 0*/


  deltaT=Gtime-p[TheParams->fwall+5].time;
#if PLATEMOVE == 0 || PLATEMOVE == -1
    wtempz = p[TheParams->fwall+5].loc.z + p[TheParams->fwall+5].vel.z * deltaT - .5 * p[TheParams->fwall+5].g * deltaT * deltaT; 
#else if PLATEMOVE == 1
    sign=copysign(1.,p[TheParams->lwall].g);
    wtempz = p[TheParams->fwall+5].loc.z + TheParams->Ampl*sin(TheParams->Omega*deltaT)*sign;
#endif
#if QFLOATS != 0
  fwrite(&wtempz,sizeof(wtempz),1,plate);
#else
  wtempz1 = (float)wtempz;
  fwrite(&wtempz1,sizeof(wtempz1),1,plate);
#endif
//  fprintf(stdout,"Fields Written at Gtime = %f\n",Gtime);    

  close_files();

 if (fmod(countf,FIELDS) == 0 || FIELDS < 1.) 
  write_restart();

 countf+=1.;


  }

#if MEASUREP==1

  if (a==TheParams->fstat+3) {

    double l,ltenl;
    double res=(2.*MAXL)/(PRES);
    int index;

    for (i=TheParams->fball;i<=TheParams->lball;i++){
        
      dt=Gtime-p[i].time;
      tempx=p[i].loc.y+p[i].vel.y*dt;
      if (tempx > YBSIZE)
       tempx -= YBSIZE;
      if (tempx < 0)
       tempx += YBSIZE;

      l=tempx+numcross[i]*YBSIZE-lastx[i];


      index=(int)(floor(l/res));
      
      index+=(int)(PRES/2);
      if ((index>=0) && (index<PRES)){
        pofl[index]+=1.;
      }
      else{
       fprintf(stdout,"%i gets away with index=%i, l=%f\n",i,index,l);
       //assert(0);
      }

      numcross[i]=0;
      lastx[i]=tempx;

    } 

 FILE *output;
 char name[30];
  strcpy(name,RUN);
  strcat(name,".pofl");
  output=fopen(name,"wb");
 fwrite(pofl,sizeof(pofl[0]),(int)PRES,output);
 fclose(output);
 
}
#endif
}

/* updates particle from its current time to newtime */

void evolve(int a,double newtime,int debug) {

#ifdef GRAVDIM
  double delt1=newtime-p[a].lgt;
  double delt2=p[a].lgt-p[a].time;
  Pvector Vo;
  Vo.x=p[a].vel.x - p[a].gvec.x * delt2;
  Vo.y=p[a].vel.y - p[a].gvec.y * delt2;
  Vo.z=p[a].vel.z - p[a].gvec.z * delt2;
  gain[p[a].cell.z-1]+=-1.*(dot(Vo,p[a].gvec)*delt1)+.5*dot(p[a].gvec,p[a].gvec)*delt1*delt1;
  p[a].lgt=newtime;
#endif

  double deltaT = newtime - p[a].time;
  p[a].loc.x = p[a].loc.x + p[a].vel.x * deltaT;
  p[a].loc.y = p[a].loc.y + p[a].vel.y * deltaT;
  p[a].loc.z = p[a].loc.z + p[a].vel.z * deltaT;
#ifdef GRAVDIM
    p[a].loc.x = p[a].loc.x - 0.5 * p[a].gvec.x * deltaT * deltaT;
    p[a].loc.y = p[a].loc.y - 0.5 * p[a].gvec.y * deltaT * deltaT;
    p[a].loc.z = p[a].loc.z - 0.5 * p[a].g * deltaT * deltaT;
    p[a].vel.x = p[a].vel.x - p[a].gvec.x * deltaT;
    p[a].vel.y = p[a].vel.y - p[a].gvec.y * deltaT;
    p[a].vel.z = p[a].vel.z - p[a].g * deltaT;
#else
  if (p[a].g > 0) {
    p[a].loc.z = p[a].loc.z - 0.5 * TheParams->g * deltaT * deltaT;
    p[a].vel.z = p[a].vel.z - TheParams->g * deltaT;
  }
#endif
#if LUDING == 1
  p[a].lasttime = p[a].time;
#endif
  p[a].time = newtime;

/*#if THERMAL == 1
  if (p[a].loc.z < INSET)
    fprintf(stdout,"%i ought to be thermal\n",a);
  if (p[a].loc.z > ZBSIZE-INSET)
    fprintf(stdout,"%i ought to be thermal\n",a);
#endif
*/

#if  PERIODIC
#if DIMENSION == 3
  while (p[a].loc.x > XBSIZE){
    p[a].loc.x -= XBSIZE; 
    numroundx[a] += 1;
   }
  while (p[a].loc.x < 0){
    p[a].loc.x += XBSIZE;
    numroundx[a] -= 1;
  }
#endif
#if PERIODIC != 2
  while (p[a].loc.y > YBSIZE){
    p[a].loc.y -= YBSIZE; 
    numroundy[a] += 1;
  }
  while (p[a].loc.y < 0){
    p[a].loc.y += YBSIZE;
    numroundy[a] -= 1;
  }
#endif
#if PERIODIC == 3
  while (p[a].loc.z > ZBSIZE){
    p[a].loc.z -= ZBSIZE; 
    numroundz[a] += 1;
  }
  while (p[a].loc.z < 0){
    p[a].loc.z += ZBSIZE;
    numroundz[a] -= 1;
  }
#endif
#endif

#if DIMENSION == 3
  assert (p[a].loc.x < p[a].cell.x);
  assert (p[a].loc.x > (p[a].cell.x-1));
#endif
  if (p[a].loc.y >= p[a].cell.y){
   fprintf(stdout,"%d %f %d\n",a,p[a].loc.y,p[a].cell.y);
   assert (p[a].loc.y < p[a].cell.y);
  }
  assert (p[a].loc.y > (p[a].cell.y-1));
  if (p[a].loc.z >= (p[a].cell.z))
   fprintf(stdout,"%i %f %i\n",a,p[a].loc.z,p[a].cell.z);
  assert (p[a].loc.z <= p[a].cell.z);
//  if (p[a].loc.z <= (p[a].cell.z-1))
//   fprintf(stdout,"%i %f %i\n",a,p[a].loc.z,p[a].cell.z);
  assert (p[a].loc.z >= (p[a].cell.z-1));

//  TheParams->etime = Gtime;
//  TheParams->update = 1;

/*  if (p[a].loc.x > p[TheParams->fwall].loc.x)
    p[a].loc.x = p[TheParams->fwall].loc.x;
  if (p[a].loc.x < p[TheParams->fwall+1].loc.x)
    p[a].loc.x = p[TheParams->fwall+1].loc.x;

  if (p[a].loc.y > p[TheParams->fwall+2].loc.y)
    p[a].loc.y = p[TheParams->fwall +2].loc.y;
  if (p[a].loc.y < p[TheParams->fwall+3].loc.y)
    p[a].loc.y = p[TheParams->fwall +3].loc.y;

  if (p[a].loc.z > p[TheParams->fwall +4].loc.z)
    p[a].loc.z = p[TheParams->fwall +4].loc.z;
  if (p[a].loc.z < p[TheParams->fwall +5].loc.z)
    p[a].loc.z = p[TheParams->fwall +5].loc.z;
*/
}

void g_evolve(double time,int debug) {
  for(int i=0;i<TheParams->nball;i++)
    if (debug)
      evolve(i,time,1);
    else
      evolve(i,time,0);
}

void vwall(int a,int debug) 
{

#ifdef GRAVDIM
  double delt1=Gtime-p[a].lgt;
  double delt2=p[a].lgt-p[a].time;
  Pvector Vo;
  Vo.x=p[a].vel.x - p[a].gvec.x * delt2;
  Vo.y=p[a].vel.y - p[a].gvec.y * delt2;
  Vo.z=p[a].vel.z - p[a].gvec.z * delt2;
  gain[p[a].cell.z-1]+=-1.*(dot(Vo,p[a].gvec)*delt1)+.5*dot(p[a].gvec,p[a].gvec)*delt1*delt1;
  p[a].lgt=Gtime;
#endif

  TheParams->NumVwall += 1;
  int b = p[a].cl->b;
  c_delete(a);
  int xcell = p[a].cell.x, ycell = p[a].cell.y, zcell = p[a].cell.z;
  if (!allocated_grid_cell_exists(xcell,ycell,zcell)) {
    fprintf(stdout,"Death in vwall before grid access\n");
    fprintf(stdout,"Particle %d is in cell %d,%d,%d. Gtime=%f\n",a,xcell,ycell,zcell,Gtime);
    bomb(4,a);
    return;
  }
/*  if(!((p[a].cell.x <= XBSIZE) && (p[a].cell.y <= YBSIZE) && (p[a].cell.z <= ZBSIZE))){
     fprintf(stdout,"Death in vwall\n");
     fprintf(stdout,"Particle %d is fucked.  Its cell is %d,%d,%d. Gtime=%f\n",a,p[a].cell.x,p[a].cell.y,p[a].cell.z,Gtime);
     bomb(4,a);}*/
  TheGrid[xcell][ycell][zcell].remove(a);
  if (b == TheParams->plusx) {
    p[a].cell.x += 1;
#if PERIODIC && (DIMENSION ==3)
    if (p[a].cell.x == XBSIZE+1){
      p[a].cell.x = 1;
    }
#endif
  }
  if (b == TheParams->negx) {
    p[a].cell.x -= 1;
#if (PERIODIC) && (DIMENSION ==3)
    if (p[a].cell.x == 0){
      p[a].cell.x = XBSIZE;
      //numroundx[a]-=1;
      //fprintf(stdout,"Now %i round x is down one to %i\n",a,numroundx[a]);
     }
#endif
  }
  if (b == TheParams->plusy) {
#if PRESSURE == 1
    pyzflux[p[a].cell.y] += p[a].vel.z-p[a].g*(Gtime-p[a].time);
#ifdef GRAVDIM
    pyyflux[p[a].cell.y] += p[a].vel.y-p[a].gvec.y*(Gtime-p[a].time);
#else
    pyyflux[p[a].cell.y] += p[a].vel.y;
#endif
#endif
    p[a].cell.y += 1;
#if PERIODIC != 2
    if (p[a].cell.y == YBSIZE+1){
      p[a].cell.y = 1;
#if MEASUREP ==1
      numcross[a]+=1;  
#endif
      //numroundy[a]+=1;
   }
#endif
  }
  if (b == TheParams->negy) {
    p[a].cell.y -= 1;
#if PERIODIC != 2
    if (p[a].cell.y == 0){
      p[a].cell.y = YBSIZE;
#if MEASUREP ==1
      numcross[a]-=1;  
#endif
      //numroundy[a]-=1;
      //fprintf(stdout,"Now %i round y is down one to %i\n",a,numroundy[a]);
}
#endif
#if PRESSURE == 1
    pyzflux[p[a].cell.y] -= p[a].vel.z-p[a].g*(Gtime-p[a].time);
#ifdef GRAVDIM
    pyyflux[p[a].cell.y] -= p[a].vel.y-p[a].gvec.y*(Gtime-p[a].time);
#else
    pyyflux[p[a].cell.y] -= p[a].vel.y;
#endif
#endif
  }


  if (b == TheParams->plusz) {
#ifdef TONLY
    slab_remove(a);
#endif
#if PRESSURE == 1
    pzzflux[p[a].cell.z] += p[a].vel.z-p[a].g*(Gtime-p[a].time);
#ifdef GRAVDIM
    pzyflux[p[a].cell.z] += p[a].vel.y-p[a].gvec.y*(Gtime-p[a].time);
#else
    pzyflux[p[a].cell.z] += p[a].vel.y;
#endif
    vzbar[p[a].cell.z] += p[a].vel.z-p[a].g*(Gtime-p[a].time);
#endif
    p[a].cell.z += 1;
#if PERIODIC == 3
    if (p[a].cell.z == ZBSIZE+1){
      p[a].cell.z = 1;
    }
#endif
#ifdef TONLY
    slab_add(a);
#endif
  }
  if (b == TheParams->negz) {
#ifdef TONLY
    slab_remove(a);
#endif
    p[a].cell.z -= 1;
#if PERIODIC == 3
    if (p[a].cell.z == 0){
      p[a].cell.z = ZBSIZE;
   }
#endif
#ifdef TONLY
    slab_add(a);
#endif
#if PRESSURE == 1
    pzzflux[p[a].cell.z] -= p[a].vel.z-p[a].g*(Gtime-p[a].time);
#ifdef GRAVDIM
    pzyflux[p[a].cell.z] -= p[a].vel.y-p[a].gvec.y*(Gtime-p[a].time);
#else
    pzyflux[p[a].cell.z] -= p[a].vel.y;
#endif
    vzbar[p[a].cell.z] += p[a].vel.z-p[a].g*(Gtime-p[a].time);
#endif
  }


  if (!physical_grid_cell_exists(p[a].cell.x,p[a].cell.y,p[a].cell.z)) {
    fprintf(stdout,"Death in vwall after virtual-cell crossing\n");
    fprintf(stdout,"Particle %d escaped to cell %d,%d,%d. Gtime=%f\n",a,p[a].cell.x,p[a].cell.y,p[a].cell.z,Gtime);
    bomb(4,a);
    return;
  }
  TheGrid[p[a].cell.x][p[a].cell.y][p[a].cell.z].add(a);


}


void vwallideal(int a) 
{
  double t_c;
  int b = p[a].cl->b;
  int xcell = p[a].cell.x, ycell = p[a].cell.y, zcell = p[a].cell.z;
  int x,y,z;
  int Num;
  fprintf(stderr,"%d WAS in [%d][%d][%d]\n",a,xcell,ycell,zcell);
  c_delete(a);
  TheGrid[xcell][ycell][zcell].remove(a);
  if (b == TheParams->plusx) {
    fprintf(stderr,"PLUSX hit!\n");
    p[a].cell.x += 1;
    for(y=-1;y<2;y++)
      for(z=-1;z<2;z++) {
	Num = TheGrid[p[a].cell.x][p[a].cell.y + y][p[a].cell.z + z].members(TheNeighbors);
	for(int i=0;i<Num;i++) {
          if (a != TheNeighbors[i]){
	    t_c = c3detect(a,TheNeighbors[i]);
	    if (t_c > Gtime)
	      c_add(a,TheNeighbors[i],t_c);}
	}
      }
  }
   
  if (b == TheParams->negx) {
    fprintf(stderr,"NEGX hit!\n");
    p[a].cell.x -= 1;
    for(y=-1;y<2;y++)
      for(z=-1;z<2;z++) {
	Num = TheGrid[p[a].cell.x][p[a].cell.y + y][p[a].cell.z + z].members(TheNeighbors);
	for(int i=0;i<Num;i++) {
          if (a != TheNeighbors[i]) {
	   t_c = c3detect(a,TheNeighbors[i]);
	   if (t_c > Gtime)
	     c_add(a,TheNeighbors[i],t_c);}
	}
      }
  }

  if (b == TheParams->plusy) {
    fprintf(stderr,"PLUSY hit!\n");

    p[a].cell.y += 1;
    for(x=-1;x<2;x++)
      for(z=-1;z<2;z++) {
	Num = TheGrid[p[a].cell.x + x][p[a].cell.y][p[a].cell.z + z].members(TheNeighbors);
	for(int i=0;i<Num;i++) {
          if (a != TheNeighbors[i]){
	   t_c = c3detect(a,TheNeighbors[i]);
	  if (t_c > Gtime) {
	    c_add(a,TheNeighbors[i],t_c);
	    fprintf(stderr,"New collision: %d will hit %d at %f.\n",a,i,t_c);
	  }
	 }
	}
      }
  }
  if (b == TheParams->negy) {
    fprintf(stderr,"NEGY hit!\n");
    p[a].cell.y -= 1;
    for(x=-1;x<2;x++)
      for(z=-1;z<2;z++) {
	Num = TheGrid[p[a].cell.x + x][p[a].cell.y][p[a].cell.z + z].members(TheNeighbors);
	for(int i=0;i<Num;i++) {
          if (a != TheNeighbors[i]){
	   t_c = c3detect(a,TheNeighbors[i]);
	  if (t_c > Gtime)
	    c_add(a,TheNeighbors[i],t_c);}
	}
      }
  }
  if (b == TheParams->plusz) {
    fprintf(stderr,"PLUSZ hit!\n");
    p[a].cell.z += 1;
    for(x=-1;x<2;x++)
      for(y=-1;y<2;y++) {
	Num = TheGrid[p[a].cell.x + x][p[a].cell.y + y][p[a].cell.z].members(TheNeighbors);
	for(int i=0;i<Num;i++) {
          if (a != TheNeighbors[i]){
	   t_c = c3detect(a,TheNeighbors[i]);
	  if (t_c > Gtime)
	    c_add(a,TheNeighbors[i],t_c);}
	}
      }
  }
  if (b == TheParams->negz) {
    fprintf(stderr,"NEGZ hit!\n");

    p[a].cell.z -= 1;
    for(x=-1;x<2;x++)
      for(y=-1;y<2;y++) {
	Num = TheGrid[p[a].cell.x + x][p[a].cell.y + y][p[a].cell.z].members(TheNeighbors);
	for(int i=0;i<Num;i++) {
          if (a != TheNeighbors[i]){
	   t_c = c3detect(a,TheNeighbors[i]);
	  if (t_c > Gtime)
	    c_add(a,TheNeighbors[i],t_c);}
	}
      }
  }
  
  TheGrid[p[a].cell.x][p[a].cell.y][p[a].cell.z].add(a);
}


double gasdev()
{
        static int iset=0;
        static double gset;
        double fac,r,v1,v2;
        double ran1();

        if  (iset == 0) {
                do {
                        v1=2.0*drand48()-1.0;
                        v2=2.0*drand48()-1.0;
                        r=v1*v1+v2*v2;
                } while (r >= 1.0 || r == 0.0);
                fac=sqrt(-2.0*log(r)/r);
                gset=v1*fac;
                iset=1;
                return v2*fac;
        } else {
                iset=0;
                return gset;
        }
}

double zdev(){
 
 return(sqrt(-2.*log(drand48())));

}

#if THERMAL == 1
void thermalize(int a,int b) {

  FILE *somebefore,*someafter;
  float tout;
//  static int topc=0,botc=0;

/*
   somebefore=fopen("gauss.pre","a");
   tout=(float)p[a].vel.y;
   fwrite(&tout,sizeof(float),1,somebefore);
   tout=(float)p[a].vel.z;
   fwrite(&tout,sizeof(float),1,somebefore);
   fclose(somebefore);
*/

  evolve(a,Gtime,0);

  if (b == TheParams->ptherm){
//   topc ++;
   p[a].vel.y = TheParams->sigt * gasdev();
   p[a].vel.z = TheParams->sigt * gasdev();
  }
  else{
//   botc ++;
   p[a].vel.y = TheParams->sigb * gasdev();
   p[a].vel.z = TheParams->sigb * gasdev();
  }


  p[a].c += 1;
/*
   someafter=fopen("gauss.post","a");
   tout=(float)p[a].vel.y;
   fwrite(&tout,sizeof(float),1,someafter);
   tout=(float)p[a].vel.z;
   fwrite(&tout,sizeof(float),1,someafter);
   fclose(someafter);
*/

}
#endif

void feedback(double energy,int avoid1,int avoid2){
#if THERMAL3 == 1

  double r;
  int fillme[2],a;
  double ea,pavmag,angle;
  float tout;
  double Einit,Efinal;
 
#ifdef YONLY
  pickn(fillme,1,avoid1,avoid2);
#else
  pickn(fillme,2,avoid1,avoid2);
#endif

  energy/=(1.*10);

  for (int i=0;i<2;i++){

    a=fillme[i];
    evolve(a,Gtime,0);

#ifdef TONLY
   slab_remove(a);
#endif

    Einit=.5*dot(p[a].vel,p[a].vel);
 
/*    ea=.5*dot(p[a].vel,p[a].vel)+energy;
    pavmag=sqrt(2.*ea);

  #if DIMENSION == 2
   r=rand();
   angle=(1.*r)/(1.*RAND_MAX)*2.*PI;  
   p[a].vel.y=pavmag*sin(angle); 
   p[a].vel.z=pavmag*cos(angle); 
  #else
   THIS HASNT BEEN WRITTEN
   abort();
  #endif
*/

#ifdef ADDTO
  p[a].vel.y+=TheParams->sigm*gasdev();
  p[a].vel.z+=TheParams->sigm*gasdev();
#else
#ifdef SPINUP
  p[a].ome.x=TheParams->sigm*gasdev();
#else
#ifdef GRADIENT 
  double fac=sqrt(p[a].loc.z/ZBSIZE*2);
  p[a].vel.y=fac*TheParams->sigm*gasdev();
  p[a].vel.z=fac*TheParams->sigm*gasdev();
#else
  p[a].vel.y=TheParams->sigm*gasdev();
#ifdef YONLY
#else
  p[a].vel.z=TheParams->sigm*gasdev();
#endif
#ifdef TONLY
  p[a].vel.z += TheSlabs[p[a].cell.z].vzbar;
  slab_add(a);
#endif
#endif
#endif
#endif

  Efinal=.5*dot(p[a].vel,p[a].vel);
 
  gain[p[a].cell.z-1]+=Efinal-Einit;


  p[a].c ++;
  lel_destroy(a,0);
  c_calc(a,0);
  fel_resort(a);
  
  }

#endif

}



#if CONSERVE == 1

void feedback(double energy,int avoid1,int avoid2){

  double r;

  int done = 0,a,b,ok;
  c_data *tmp;

 while (!done){
  a=avoid1;
  while (a==avoid1 || a == avoid2){
      r=rand();
      a=(int)(1.*r*(TheParams->nball)/(RAND_MAX));
   }

/*Choose a second particle near the first particle*/

  tmp = p[a].cl;
  ok = 0;
  while (!ok){
   if (tmp==NULL)
    ok = 1;
   else if (p[tmp->b].pty == SPHERE)
    ok = 1;
   else 
    tmp = tmp->cnext;
  }
  if (tmp != NULL){
    b=tmp->b;
    done=1;
  }

 }

/*  
  Choose a second particle at random
  int b=a;
  while (b==a || b == avoid1 || b==avoid2){
  r=rand();
  b=(int)(1.*r*(TheParams->nball)/(RAND_MAX));
  }
*/

  double oldE=.5*(dot(p[a].vel,p[a].vel)+dot(p[b].vel,p[b].vel));

  evolve(a,Gtime,0);
  evolve(b,Gtime,0);

  energy;

  double DVY=p[a].vel.y-p[b].vel.y;
  double DVZ=p[a].vel.z-p[b].vel.z;
  double SVY=p[a].vel.y+p[b].vel.y;
  double SVZ=p[a].vel.z+p[b].vel.z;
  double alpha=SVY/SVZ;
  double Aterm=(1+alpha*alpha);
  double Bterm=(DVY-alpha*DVZ);
  double Cterm=-energy;

  double Bsqr_4ac = Bterm * Bterm - 4. * Aterm * Cterm;
  if (Bsqr_4ac < 0){
    fprintf(stdout,"Cant be done.  Get smarter.\n");
    abort(); 
  }
  
   double sb,q,r1,r2;
   if (Bterm < 0)
      sb = -1.;
   else
     sb = 1.;


   q = -.5*(Bterm + sb * sqrt(Bsqr_4ac));
   r1 = q/Aterm;
   r2 = Cterm/q;

   double deltaVy=r1;
   double deltaVz=-alpha*r1;

   p[a].vel.y+=deltaVy;
   p[b].vel.y-=deltaVy;
   p[a].vel.z+=deltaVz;
   p[b].vel.z-=deltaVz;

  double newE=.5*(dot(p[a].vel,p[a].vel)+dot(p[b].vel,p[b].vel));

//  fprintf(stdout,"%f %f %f\n",oldE+energy,newE,oldE+energy-newE);

  p[a].c ++;
  p[b].c ++;
  lel_destroy(a,0);
  lel_destroy(b,0);
  c_calc(a,0);
  c_calc(b,0);
  fel_resort(a);
  fel_resort(b);

}

#endif

void pickn(int *fillme,int n,int avoid1,int avoid2){

  double r;
  int index;

  for (int i=0;i<n;i++) {

    int a=avoid1;
    while (a==avoid1 || a == avoid2){
        r=rand();
        index=(int)(1.*r*(TheParams->nball-i)/(RAND_MAX));
        a=listarray[index];
        assert(a <= TheParams->lball);
    }
    fillme[i]=a;
    listarray[index]=listarray[TheParams->nball-i-1];
    listarray[TheParams->nball-i-1]=fillme[i];

  }

  /*fprintf(stdout,"not %d %d\n",avoid1,avoid2);
  fprintf(stdout,"%d %d %d %d %d\n",fillme[0],fillme[1],fillme[2],fillme[3],fillme[4]);
  fprintf(stdout,"%d %d %d %d %d\n",fillme[5],fillme[6],fillme[7],fillme[8],fillme[9]);
*/

}

#if THERMAL4 == 1

void fluctforce(int nogo,int b){

  double totgy=0,totgz=0;
  double mag;
  double ry,rz;
  double angle,distance;
  double dist;
  int bb;
  int npick=1;
  PVECTOR rabhat;
  if (nogo != -1)
   npick=2;
  int rate=2*npick;

  int fillme[npick],a;

  if (nogo == -1)
    pickn(fillme,npick,-99,-99);
  else{
    fillme[0]=nogo;
    fillme[1]=b;
  }
  for (int i=0;i<rate;i++){

    if (i<npick){
     a=fillme[i];
    }
    else {
     if (fillme[i-npick] < TheParams->nball/2)
      a=fillme[i-npick]+TheParams->nball/2;
     else
      a=fillme[i-npick]-TheParams->nball/2;
    }

    evolve(a,Gtime,0);

    if (i<npick){
     if (nogo == -1){
#if GRADIENT == 1 /*THERMAL GRADIENT IN Z*/
        angle=drand48()*2.*PI;  
        dist=ZBSIZE/2.-fabs(ZBSIZE/2. - p[a].loc.z);
        p[a].gvec.y = TheParams->sigm*dist*cos(angle);
        p[a].gvec.z = TheParams->sigm*dist*sin(angle);
#else 
  #if GRADIENT == 2 /*VY GRADIENT IN Z*/
      p[a].gvec.y = TheParams->sigm*(.01*sin(2*PI*p[a].loc.z/ZBSIZE)+gasdev());
   //    p[a].gvec.y = TheParams->sigm*(.1*sin(2*PI*p[a].loc.z/ZBSIZE));
//        p[a].gvec.z = 0;
        p[a].gvec.z = TheParams->sigm*gasdev();
  #else /*NO GRADIENT*/
    #if METHOD == 0
        angle=drand48()*2.*PI;  
        p[a].gvec.y = TheParams->sigm*cos(angle);
        p[a].gvec.z = TheParams->sigm*sin(angle);
    #else
        p[a].gvec.y = TheParams->sigm*gasdev();
        p[a].gvec.z = TheParams->sigm*gasdev();
    #endif
   #endif
#endif /*GRADIENT*/
       }
     else{
       bb=fillme[1-i];
       rabhat.x = 0;
       rabhat.y=p[bb].loc.y-p[a].loc.y;
       rabhat.z=p[bb].loc.z-p[a].loc.z;
       distance=sqrt(dot(rabhat,rabhat));
       rabhat.y/=distance;
       rabhat.z/=distance;
       rabhat.y*=TheParams->sigm;
       rabhat.z*=TheParams->sigm;
       p[a].gvec.y=rabhat.y;
       p[a].gvec.z=rabhat.z;
     }
    }

    else{
     p[a].gvec.y = -p[fillme[i-npick]].gvec.y;
     p[a].gvec.z = -p[fillme[i-npick]].gvec.z;
    }

    p[a].g = p[a].gvec.z;
    p[a].c ++;
    lel_destroy(a,0);
    c_calc(a,0);
    fel_resort(a);
  }

/* for (int q=0;q<TheParams->nball/2-1;q++){
   assert(p[q].gvec.y == - p[q+TheParams->nball/2].gvec.y);
   assert(p[q].gvec.z == - p[q+TheParams->nball/2].gvec.z);
 }
*/

}

/*END FLUCTFORCE*/


/*This one looks like it works
void fluctforce(){

  double totgy=0,totgz=0;
  double mag;
  double ry,rz;

  int fillme[2],a;
  pickn(fillme,2,-99,-99);
  for (int i=0;i<2;i++){
    if (i==0)
     a=fillme[i];
    else {
     if (a < TheParams->nball/2)
      a=fillme[0]+TheParams->nball/2;
     else
      a=fillme[0]-TheParams->nball/2;
    }
    evolve(a,Gtime,0);
    p[a].gvec.y *= -1;
    p[a].gvec.z *= -1;
    p[a].g = p[a].gvec.z;
    p[a].c ++;
    lel_destroy(a,0);
    c_calc(a,0);
    fel_resort(a);
  }
}
*/

/*
void fluctforce(){

  double totgy=0,totgz=0;
  double mag;
  double ry,rz;

  ry = theparams->sigm*gasdev();
  rz = theparams->sigm*gasdev();

  int fillme[2],a;
  pickn(fillme,2,-99,-99);
  for (int i=0;i<2;i++){
    a=fillme[i];
    evolve(a,Gtime,0);
    p[a].gvec.y += 2*(i-.5)*ry;
    p[a].gvec.z += 2*(i-.5)*rz;
    p[a].g = p[a].gvec.z;
    p[a].c ++;
    lel_destroy(a,0);
    c_calc(a,0);
    fel_resort(a);
  }
}
*/


/*
void fluctforce(){

  double totgy=0,totgz=0;
  double mag;
  double ry,rz;

  int fillme[2],a;
  pickn(fillme,2,-99,-99);
  for (int i=0;i<2;i++){
    a=fillme[i];
    evolve(a,Gtime,0);
    p[a].gvec.y = TheParams->sigm*gasdev();
    p[a].gvec.z = TheParams->sigm*gasdev();
    p[a].g = p[a].gvec.z;
    p[a].c ++;
    lel_destroy(a,0);
    c_calc(a,0);
    fel_resort(a);
  }
}
*/


#endif
