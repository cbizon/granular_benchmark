#include "main.h"
#include "plist.h"
#include "cell.h"
#include "string.h"
#include "collide.h"
#include <math.h>
#include <iostream>
using namespace std;
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>


extern P_DATA p[];
extern double Gtime,Stime;
extern CellSet TheGrid[XGSIZE][YGSIZE][ZGSIZE];
extern ParamStructPtr TheParams;
extern FILE *starter;
extern double leftp,rightp,frontp,backp,midpx,midpy,radp;
#if MEASUREP == 1
extern double pofl[],lastx[];
extern int numcross[];
#endif
#if PERIODIC 
extern double startx[];
extern int numroundx[];
extern double starty[];
extern int numroundy[];
extern double startz[];
extern int numroundz[];
#endif
#if GK == 1
extern vinit[];
#endif
#ifdef TONLY
extern slab TheSlabs[ZGSIZE];
#endif

/* pl_init()
Need to add call to srand to change random lists...
*/

void pl_init( void ) {
  int badpart;
  double Dt,Dz;
  int i,j,xcell,ycell,zcell,part,nmore,count;
  double rows,ballsperrow,fullrows,yspace,zheight,zzero;
  double dum,oldparms[3],platexvat[4],xspace,fac,nx;
  double k,l,ballsperlayer,nleft,fulllayers,nballsfull,rowsperlayer;
  char name[50];
  double deltaT,tempx,tempy,tempz;
  double angle;
#if ZEROMOM
  double totalpy=0.,totalpz=0.;
#endif
  double ntempx,ntempy,ntempz;

  Gtime = 0.0;
  fprintf(stdout,"setting up %d particles out of a possible %d\n",TheParams->nball,(NMOV + NJUNK));
  TheParams->Initialized = 1;
#if START == 0
//#if RANDOM != -99
  srand48(RANDOM);  /* set up reproducible pseudo-random sequence */
//#else
//  time_t thetime;	/* if random, base the seed value on the current */
//  thetime = time(NULL); /* system time */
//  srand48(thetime);
//#endif

#if (DIMENSION == 2 || ((DIMENSION == 3 )  && (QUASI == 1)))

  rows = floor((TheParams->lball*(PDIAM+PDISP))/((double)YBSIZE)) + 5;
  fprintf(stdout,"YYOYOYO\n");
#ifdef DENSIFY
  ballsperrow = floor(TheParams->lball/rows)-1;
#else
  ballsperrow = floor(TheParams->lball/rows)+2;
#endif
//  ballsperrow=52;
  fullrows = floor(TheParams->lball/ballsperrow);
  yspace=YBSIZE/(1.+ballsperrow);
  fprintf(stdout,"%f balls per row\n",ballsperrow);

#else 
#if ((DIMENSION == 3) && (QUASI != 1))
 
  ballsperrow = floor((.75*(double)YBSIZE)/(PDIAM));
  fprintf(stdout,"%f balls per row\n",ballsperrow);
  
  rowsperlayer= floor((.75*(double)XBSIZE)/(PDIAM));
  if (rowsperlayer == 0.)
    if (PDIAM < XBSIZE) 
      rowsperlayer = 1.; 
  ballsperlayer=ballsperrow*rowsperlayer; 
  fprintf(stdout,"%f rows per layer\n",rowsperlayer);
  fprintf(stdout,"%f balls per layer \n",ballsperlayer);
  
  fulllayers=floor(TheParams->lball/ballsperlayer);
  fprintf(stdout,"%f\n",fulllayers);
  
  nballsfull=ballsperlayer*fulllayers;
  fprintf(stdout,"%f\n",nballsfull);
  
  yspace=(double)YBSIZE/(1.+ballsperrow);

  fprintf(stdout,"Setting up particle placement\n");

#else if DIMENSION == 1

#endif
#endif

/*  zzero= .125 * TheParams->g * TheParams->Period * TheParams->Period + 2.0 * TheParams->Ampl;
*/

/* The normal zzero: Remember to put this back*/
#if ZZERONORM == 0
  zzero=TheParams->Ampl + PDIAM * .55;
/* Give 'em a good drop: */
#else
  zzero = 20.;
#endif

#if (DIMENSION == 2 || ((DIMENSION == 3 )  && (QUASI == 1)))

  double shift=.25;
/*
#if PERIODIC == 3  
  double space,zspace,yb,layer,oddeven;
  ballsperrow=(int)(YBSIZE/0.961);
  space=((float)YBSIZE)/((float)(ballsperrow));
  zspace=space*sqrt(3.)/2.+0.001;
  for (i=0;i<=TheParams->lball;i++){
    layer = (int)(i/ballsperrow);
    oddeven=fmod(layer,2);
    yb=i-layer*ballsperrow;
    p[i].loc.y=.1+oddeven*space/2.+yb*space;
    p[i].loc.z=zspace/2.+layer*zspace;
    if (ZBSIZE-(p[i].loc.z)<zspace/2.){
        fprintf(stdout,"What am I, some kind of packing genius?\n");
        fprintf(stdout,"For particle %d, z=%f\n",i,p[i].loc.z);
        abort();
    }
  }
#else
*/
#ifdef DENSIFY 
  double space,zspace,yb,layer,oddeven;
  ballsperrow=(int)(YBSIZE/0.961)-2;
  space=((float)YBSIZE)/((float)(ballsperrow));
  zspace=space*sqrt(3.)/2.+0.01;
  for (i=0;i<=TheParams->lball;i++){
    layer = (int)(i/ballsperrow);
    oddeven=fmod(layer,2);
    yb=i-layer*ballsperrow;
    p[i].loc.y=.1+oddeven*space/2.+yb*space;
    p[i].loc.z=0.5+layer*zspace;
    if (ZBSIZE-(p[i].loc.z)<zspace/2.){
        fprintf(stdout,"What am I, some kind of packing genius?\n");
        fprintf(stdout,"For particle %d, z=%f\n",i,p[i].loc.z);
        abort();
    }
  }
#else
  for (i=0;i<fullrows;i++){
    shift=-1.*shift;
    zheight = i *1.25*(PDIAM+PDISP)+zzero;
//    zheight = i *0.95*(PDIAM+PDISP)+zzero;
    for (j=0;j<ballsperrow;j++){
      p[(int)(i*ballsperrow+j)].loc.y = (j+1+shift) * yspace + drand48() * PDIAM * .05;
//      p[(int)(i*ballsperrow+j)].loc.y = (j+.25+shift) * yspace + drand48() * PDIAM * .05;
      p[(int)(i*ballsperrow+j)].loc.z = zheight + drand48() * PDIAM * .05;
      if (p[(int)(i*ballsperrow+j)].loc.z > ZBSIZE - PDIAM/2.){
        fprintf(stdout,"What am I, some kind of packing genius?\n");
        fprintf(stdout,"For particle %d, z=%f\n",(int)(i*ballsperrow+j),p[(int)(i*ballsperrow+j)].loc.z);
        abort();
        }/*Ball outside*/
    }/*loop j*/
  }/*loop i*/
#endif
//#endif

  if (TheParams->lball-fullrows*ballsperrow+1 != 0.){
#ifdef DENSIFY 
    zheight = ZBSIZE - zzero;
#else
    zheight = fullrows * 1.25 * (PDIAM+PDISP) + zzero;
#endif
    yspace = YBSIZE/(2.+(int)TheParams->lball-fullrows*ballsperrow);
    for (j=0;j<=(TheParams->lball-fullrows*ballsperrow+1);j++){
      p[(int)(fullrows*ballsperrow+j)].loc.y = (j+1) * yspace + drand48() * PDIAM * .05;
      p[(int)(fullrows*ballsperrow+j)].loc.z = zheight + drand48() * PDIAM * .05;
//      printf("%i, %f, %f \n",(int)(fullrows*ballsperrow+j),p[(int)(fullrows*ballsperrow+j)].loc.y,p[(int)(fullrows*ballsperrow+j)].loc.z);
    }
  }

#else 
#if ((DIMENSION == 3) && (QUASI != 1))

part=0;

  if (rowsperlayer != 1.){ 
    //xspace=yspace;
    xspace=(double)(XBSIZE)/(1.*rowsperlayer+1.);
    fprintf(stdout,"xspace=%f\n",xspace);
    fac=(xspace-PDIAM)/4.;}
  else{ 
    xspace=0.5;
//    fac=0.1*(0.5-PDIAM/2.);
    fac=0.;}

fprintf(stdout,"Xspace: %f Yspace: %f\n",xspace,yspace);

if (rowsperlayer == 1.){
  for (i=0;i<fulllayers+2;i++){
   for (k=xspace;k<(XBSIZE-PDIAM/2.);k+=xspace){
    for (l=yspace;l<(YBSIZE-PDIAM/2.);l+=yspace){
     if (part <= TheParams->lball) {
      p[part].loc.x = k + drand48() * fac;
      p[part].loc.y = l + drand48() * PDIAM *.05;
      p[part].loc.z = zzero + i * 1.3 * PDIAM + drand48() * PDIAM * .05;
      part += 1; }
   }}}}
else {
   double shift=xspace/4.;
   for (i=0;i<fulllayers;i++){
    shift=-1.*shift;
    fprintf(stdout,"layer: %i particles down: %i\n",i,part);
   for (k=xspace+shift;k<(XBSIZE-PDIAM/2.);k+=xspace){
    for (l=yspace+shift;l<(YBSIZE-PDIAM/2.);l+=yspace){
     if (part <= TheParams->lball) {
      p[part].loc.x = k + drand48() * fac ;
      p[part].loc.y = l + drand48() * PDIAM *.05 ;
      p[part].loc.z = zzero + i * 1.3 * PDIAM + drand48() * PDIAM * .05;
      part += 1; }}}} 
 
   fprintf(stdout,"Placed particles up to but not including # %i\n",part);

   nmore=TheParams->lball-part+1;

   fprintf(stdout,"So there are %i left\n",nmore);

     if (nmore == ballsperlayer) {
     fprintf(stdout,"Add another full layer\n"); 
     for (k=xspace/2.;k<(XBSIZE-PDIAM/2.);k+=xspace){
       for (l=yspace;l<(YBSIZE-PDIAM/2.);l+=yspace){
          p[part].loc.x = k + drand48() * fac;
          p[part].loc.y = l + drand48() * PDIAM *.05; 
          p[part].loc.z = zzero + fulllayers * 1.3 * (PDIAM+PDISP) + drand48() * PDIAM * .05;
          part += 1;
          count += 1;}}
     nmore = TheParams->lball-part+1;
     fprintf(stdout,"So there are %i left\n",nmore);
     }

   if (nmore != 0){

     nx=floor(sqrt(((1.*XBSIZE)/(1.*YBSIZE))*nmore));
     double ny=floor(sqrt(((1.*YBSIZE)/(1.*XBSIZE))*nmore));

     xspace = (1.*XBSIZE)/(1.*(nx))-0.001;
     yspace = (1.*YBSIZE)/(1.*(ny))-0.001;


     fprintf(stdout,"xspace: %f yspace: %f\n",xspace,yspace);
 
     assert(xspace > 1.1 * PDIAM);
     assert(yspace > 1.1 * PDIAM);

     count = 0;
     for (k=xspace/2.;k<=(XBSIZE-xspace/2.);k+=xspace){
       for (l=yspace/2.;l<=(YBSIZE-yspace/2.);l+=yspace){
          p[part].loc.x = k + drand48() * fac;
          p[part].loc.y = l + drand48() * PDIAM *.05; 
          p[part].loc.z = zzero + fulllayers * 1.3 * (PDIAM+PDISP) + drand48() * PDIAM * .05;
          part += 1;
          count += 1;}}
     
     fprintf(stdout,"Placed %i balls in a square layer\n",count);

     nmore = TheParams->lball-part+1;
  
     fprintf(stdout,"So there are %i left\n",nmore);


 
     if (nmore != 0) {
      
       assert (nmore+1 <= YBSIZE);
       yspace = (1.*YBSIZE)/(1.*(nmore+1));
       for (l=yspace;l<(YBSIZE-PDIAM/2.);l+=yspace){
          p[part].loc.x = (drand48() * (XBSIZE-2))+1.;
          p[part].loc.y = l+.0001 ;
          p[part].loc.z = zzero + (1.+fulllayers) * 1.3 * (PDIAM+PDISP) + drand48() * PDIAM * .05;
          part += 1;}

     assert (part==TheParams->lball+1);
     }
  }
 
}

if (part == TheParams->lball+1)
  fprintf(stdout,"Placed all balls (distributed)\n");
else
  fprintf(stdout,"Something is screwed in the placement counting\n");

/* fprintf(stdout,"Placed full layers\n");

( nleft=TheParams->lball-part+1;
 ballsperrow=ceil(sqrt(nleft));
 yspace=YBSIZE/(1.+ballsperrow);
 zzero += fulllayers*1.5*PDIAM;

 k=yspace;
 l=yspace;

 fprintf(stdout,"Set up partial layer\n");

 for (i=part;i<=TheParams->lball;++i) {
    p[i].loc.x =  k + drand48() * PDIAM * .05;
    p[i].loc.y =  l + drand48() * PDIAM * .05; 
    p[i].loc.z = zzero + drand48() * PDIAM * .05;
    k += yspace;
    if (k > XBSIZE-yspace){
      k=yspace;
      l+=yspace;
    }
  }

 fprintf(stdout,"Placed partial layer\n"); */

#else if DIMENSION == 1
double zh=TheParams->Ampl+1.1;
 for (i=0;i<=TheParams->lball;++i){
  p[i].loc.x=0.5;
  p[i].loc.y=0.5;
  zh += PDIAM + fabs(drand48());
  p[i].loc.z=zh;
  p[i].vel.x=p[i].vel.y=0.;   
  p[i].vel.z=TheParams->Ampl*TheParams->Omega*(drand48()-.5);
  p[i].g = TheParams->g;
  fprintf(stdout,"Particle %i at z=%f and vz=%f\n",i,p[i].loc.z,p[i].vel.z);
 }
#endif
#endif


//#if RANDOM == 1
//  fprintf(stdout,"pl_init: random seed %d \n ",thetime);
//#else
  fprintf(stdout,"pl_init: pseudorandom seed\n");
//#endif

  for(i=TheParams->fball;i<=TheParams->lball;++i) {
    p[i].diam = PDIAM * (1. + 2. * PDISP * (drand48() - .5) );
#if QUASI == 1
    if (p[i].diam > 1.-2.*WOFFSET)
     assert(p[i].diam <= 1.-2.*WOFFSET);
#endif   
    p[i].g = TheParams->g; 
#ifdef GRAVDIM
   if (i<TheParams->nball/2){
    angle=drand48()*2*PI;
    p[i].gvec.y=TheParams->sigm*sin(angle);
    p[i].g=TheParams->sigm*cos(angle);
   }
   else{
    p[i].gvec.y=-p[i-TheParams->nball/2].gvec.y;
    p[i].g=-p[i-TheParams->nball/2].g;
   }
   p[i].gvec.x=0;
   p[i].gvec.z=p[i].g;
#endif
#if (DIMENSION == 2 || ((DIMENSION == 3 )  && (QUASI == 1)))
    p[i].loc.x = 0.5;
#endif
//    printf("Particle %i has diameter %f\n",i,p[i].diam);
if (TheParams->Ampl != 0)
    p[i].vel.z = 0.1 * (drand48() - 0.5);
else{
    p[i].vel.z = (drand48()-0.5)*MAX_VEL*2;
#if (THERMAL2 == 1 || PERIODIC == 3 || GRADIENT == 1)
  if (TheParams->BallRest != 1.){
     if ((TOPT == -1) || (BOTT == -1)){
      p[i].vel.y = .5*(SIGM)*gasdev();
      p[i].vel.z = .5*(SIGM)*gasdev();
     }
     else{
      p[i].vel.y = .5*(SIGB+SIGT)*gasdev();
      p[i].vel.z = .5*(SIGB+SIGT)*gasdev();
    }
  }
  else{
    p[i].vel.y = SIGM*(2*fmod((double)i,2.)-1.);
    p[i].vel.z = SIGM*(2*fmod(fmod((double)i,4.),2)-1.);
  }
#endif 
  if (TheParams->BallRest == 1.){
    p[i].vel.y = SIGM*(2*fmod((double)i,2.)-1.);
    p[i].vel.z = SIGM*(2*fmod(fmod((double)i,4.),2)-1.);
  }
}
/*#if DIMENSION == 3
    p[i].vel.x = 1*drand48();
#else
    p[i].vel.x = 0.;
#endif
    p[i].vel.y = .1*drand48();
*/

/*
#if DIMENSION == 3
if (fmod((double)i,2.) == 0){
  p[i].vel.x = 5.*drand48();
  p[i].vel.y = 5.*drand48();
}
else{
  p[i].vel.x = -1*p[i-1].vel.x;
  p[i].vel.y = -1*p[i-1].vel.y;
}
#endif

#if (DIMENSION == 2 || (DIMENSION == 3 && QUASI == 1))
if (fmod((double)i,2.) == 0){
  p[i].vel.x = 0.;
  p[i].vel.y = 5.*drand48();
}
else{
  p[i].vel.x = 0.;
  p[i].vel.y = -1*p[i-1].vel.y;
}
#endif
*/

   p[i].vel.x=0.;
if (TheParams->Ampl != 0)
   p[i].vel.y=0.;

#if ROTATIONS == 1
   p[i].ome.x=0.;
   p[i].ome.y=0.;
   p[i].ome.z=0.;
#endif

/*#if QUASI == 1
   p[i].vel.x = .1*(drand48()-0.5);
#endif
*/

/*    p[i].loc.y = drand48() * BSIZE * 0.9 + BSIZE * 0.05;
    p[i].loc.z = 0.45 * drand48() * BSIZE * 0.9 + BSIZE * 0.05;
*/
 
    
   
/*    if (TheParams->View3D == 1)
      p[i].loc.x = drand48() * BSIZE * 0.9 + BSIZE * 0.05;
    else
      p[i].loc.x = 0.5;*/
    
#if PERIODIC != 3
    if (p[i].loc.z <= PRAD + WOFFSET)
      p[i].loc.z += 1.;
#endif

    xcell = p[i].cell.x = (int) p[i].loc.x + 1;
    ycell = p[i].cell.y = (int) p[i].loc.y + 1;
    zcell = p[i].cell.z = (int) p[i].loc.z + 1;
    TheGrid[xcell][ycell][zcell].add(i);

    p[i].c = 0;
    p[i].wallcalc = 0;

//#if FOLLOW == 1
//    if (i == THIS){
//      fprintf(stdout,"x:%f y:%f z:%f",p[i].loc.x,p[i].loc.y,p[i].loc.z);
//      fprintf(stdout,"xc:%i yc:%i zc:%i,p[i].cell.x,p[i].cell.y,p[i].cell.z);
//     }
//#endif
   
#if FOLLOW == 1
    if (i == THIS ){
     fprintf(stdout,"i: %d, xc: %d, yc: %d, zc: %d pdiam: %f\n",i,p[i].cell.x,p[i].cell.y,p[i].cell.z,p[i].diam);
     fprintf(stdout,"x: %f y: %f z:%f vx:%f vy:%f vz:%f\n",p[i].loc.x,p[i].loc.y,p[i].loc.z,p[i].vel.x,p[i].vel.y,p[i].vel.z);
      }
#endif
 
//    if (TheParams->View3D == 1)
//      p[i].vel.x = (drand48() - 0.5) * MAX_VEL;
//    else
//      p[i].vel.x = 0.0;
    
//    p[i].vel.y = (drand48() - 0.5) * MAX_VEL;
//    p[i].vel.z = 0.05 * (drand48() - 0.5) * MAX_VEL;
    p[i].cl = NULL;
    p[i].pty = SPHERE;
    p[i].time = 0;
#ifdef GRAVDIM
   p[i].lgt = p[i].time;
   p[i].vel.y = p[i].vel.z = 0;
#endif
#if LUDING == 1
    p[i].lasttime = 0;
#endif
//    fprintf(stdout,"%d, %f, %f\n",i,p[i].loc.y,p[i].loc.z);
  }

#if ZEROMOM
  for (i=0;i<TheParams->lball;i++){
    totalpy+=p[i].vel.y;  
    totalpz+=p[i].vel.z;  
  }
  p[TheParams->lball].vel.y = -totalpy;
  p[TheParams->lball].vel.z = -totalpz;
#endif
#ifdef GRAVDIM
  double totgy=0,totgz=0;
  for (i=0;i<TheParams->lball;i++){
    totgy+=p[i].gvec.y;  
    totgz+=p[i].gvec.z;  
  }
  p[TheParams->lball].gvec.y = -totgy;
  p[TheParams->lball].gvec.z = -totgz;
#endif
 
#else 
#if START == 1
  strcpy(name,OLDRUN);
  strcat(name,".restart");
  starter=fopen(name,"rb");
  if (NULL == starter)
    assert(3==100);
  printf("Opened Restart File\n");
  fread(&oldparms[0],sizeof(oldparms[0]),1,starter);
  fread(&oldparms[1],sizeof(oldparms[1]),1,starter);
  fread(&oldparms[2],sizeof(oldparms[2]),1,starter);                
  fread(&Gtime,sizeof(Gtime),1,starter);
  
  Stime=Gtime;
 
  for(i=TheParams->fball;i<=TheParams->lball;++i) {  
    badpart=0;
    fread(&p[i].diam,sizeof(p[i].diam),1,starter);  
    fread(&p[i].loc.x,sizeof(p[i].loc.x),1,starter);
    fread(&p[i].loc.y,sizeof(p[i].loc.x),1,starter);
    fread(&p[i].loc.z,sizeof(p[i].loc.x),1,starter);
    fread(&p[i].vel.x,sizeof(p[i].loc.x),1,starter);
    fread(&p[i].vel.y,sizeof(p[i].loc.x),1,starter);
    fread(&p[i].vel.z,sizeof(p[i].loc.x),1,starter);
    fread(&p[i].cell.x,sizeof(p[i].cell.x),1,starter);
    fread(&p[i].cell.y,sizeof(p[i].cell.y),1,starter);
    if (p[i].cell.y > YBSIZE){
       badpart=1;
       fprintf(stdout,"%i %i %f\n",i,p[i].cell.y,p[i].loc.y); 
    } 
    fread(&p[i].cell.z,sizeof(p[i].cell.z),1,starter);
    fread(&p[i].time,sizeof(p[i].time),1,starter);
#ifdef GRAVDIM
   p[i].lgt = p[i].time;
#endif
#if LUDING == 1
    p[i].lasttime=0;
#endif
#ifdef GRAVDIM
    fread(&p[i].gvec.x,sizeof(p[i].g),1,starter); 
    fread(&p[i].gvec.y,sizeof(p[i].g),1,starter); 
    fread(&p[i].gvec.z,sizeof(p[i].g),1,starter); 
    p[i].g = p[i].gvec.z;
#else
    fread(&p[i].g,sizeof(p[i].g),1,starter); 
#endif
#if ROTATIONS == 1
    fread(&p[i].ome.x,sizeof(p[i].loc.x),1,starter);
    fread(&p[i].ome.y,sizeof(p[i].loc.x),1,starter);
    fread(&p[i].ome.z,sizeof(p[i].loc.x),1,starter);
#endif
    if (badpart){
      p[i].loc.y=YBSIZE-p[i].loc.y; 
      p[i].time=Stime; 
      p[i].cell.y = (int) p[i].loc.y + 1;
      p[i].loc.z=40.5; 
      p[i].cell.z=41;
    }
 
    Dt=Stime-p[i].time;
    Dz=-TheParams->Ampl-WOFFSET+(p[i].loc.z-p[i].diam/2.+p[i].vel.z*Dt-.5*p[i].g*Dt*Dt);

      deltaT=Dt;
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
 

    if (Dz < 0){
     fprintf(stdout,"%f\n",p[i].loc.z-p[i].diam/2.+p[i].vel.z*Dt-.5*p[i].g*Dt*Dt);
     fprintf(stdout,"%f %f %f %f\n",p[i].loc.z,p[i].vel.z,Dt,p[i].g);
     fprintf(stdout,"Leaky plate: %d Dz:%f Dt:%f\n",i,Dz,Dt);
     fprintf(stdout,"Plate: %f, Ball: %f\n",TheParams->Ampl+WOFFSET,+p[i].loc.z-p[i].diam/2.);

     }

/*    if (p[i].loc.x-p[i].diam/2.-WOFFSET < 0.){
     fprintf(stdout,"Boy this restart file sucks.\n");
     fprintf(stdout,"Particle %d had to be rounded up and put into the box.\n",i);
     fprintf(stdout,"error:%g\n",p[i].loc.x-p[i].diam/2.-WOFFSET);
     fprintf(stdout,"x: %f y: %f z: %f\n",p[i].loc.x, p[i].loc.y,p[i].loc.z);
     fprintf(stdout,"x: %f y: %f z: %f\n",p[i].vel.x, p[i].vel.y,p[i].vel.z);
     p[i].loc.x = 2.5;
     p[i].loc.z = 30.;}

    if (p[i].loc.x+p[i].diam/2.+WOFFSET > XBSIZE){
     fprintf(stdout,"Boy this restart file sucks.\n");
     fprintf(stdout,"Particle %d had to be rounded up and put into the box.\n",i);
     fprintf(stdout,"error:%g\n",p[i].loc.x+p[i].diam/2.+WOFFSET);
     fprintf(stdout,"x: %f y: %f z: %f\n",p[i].loc.x, p[i].loc.y,p[i].loc.z);
     fprintf(stdout,"x: %f y: %f z: %f\n",p[i].vel.x, p[i].vel.y,p[i].vel.z);
     p[i].loc.x = XBSIZE-1.5;
     p[i].loc.z = 30.;}

    if (p[i].loc.y+p[i].diam/2.+WOFFSET > YBSIZE){
     fprintf(stdout,"Boy this restart file sucks.\n");
     fprintf(stdout,"Particle %d had to be rounded up and put into the box.\n",i);
     fprintf(stdout,"error:%g\n",p[i].loc.y+p[i].diam/2.+WOFFSET-YBSIZE);
     fprintf(stdout,"x: %f y: %f z: %f\n",p[i].loc.x, p[i].loc.y,p[i].loc.z);
     fprintf(stdout,"x: %f y: %f z: %f\n",p[i].vel.x, p[i].vel.y,p[i].vel.z);
     p[i].loc.y = YBSIZE-1.5;
     p[i].loc.z = 30.;}

    if (p[i].loc.y-p[i].diam/2.-WOFFSET< 0.){
     fprintf(stdout,"Boy this restart file sucks.\n");
     fprintf(stdout,"error:%g\n",p[i].loc.y-p[i].diam/2.-WOFFSET-XBSIZE);
     fprintf(stdout,"x: %f y: %f z: %f\n",p[i].loc.x, p[i].loc.y,p[i].loc.z);
     fprintf(stdout,"x: %f y: %f z: %f\n",p[i].vel.x, p[i].vel.y,p[i].vel.z);
     fprintf(stdout,"Particle %d had to be rounded up and put into the box.\n",i);
     p[i].loc.y = 2.5;
     p[i].loc.z = 30.;}
*/
    
    p[i].cl = NULL;
    p[i].pty = SPHERE;
    xcell = p[i].cell.x; //= (int) p[i].loc.x + 1;
    ycell = p[i].cell.y; //= (int) p[i].loc.y + 1;
    zcell = p[i].cell.z; //= (int) p[i].loc.z + 1;
    TheGrid[xcell][ycell][zcell].add(i);             
    p[i].c = 0;
    p[i].wallcalc = 0;
#if FOLLOW == 1
    if (i == THIS ){
     fprintf(stdout,"i: %d, xc: %d, yc: %d, zc: %d\n",i,p[i].cell.x,p[i].cell.y,p[i].cell.z);
     fprintf(stdout,"y: %f z:%f vy:%f vz:%f\n",p[i].loc.y,p[i].loc.z,p[i].vel.y,p[i].vel.z);
     fprintf(stdout,"Time: %f\n",p[i].time);
      }
#endif
     } 
#else if START == 2
  int eo,nincol,pz;
  double basex,basey; 
  strcpy(name,OLDRUN);
  strcat(name,".nprof");
  starter=fopen(name,"rb");
  printf("Opened Nprof File\n");
  Stime=Gtime;
  short nprof[100][100];
  for (int step=0;step<=FRAME;step++){
   fread(nprof,sizeof(nprof[0][0]),10000,starter);
  fprintf(stdout,"Got a frame\n");
  long total=0;
  for (i=0;i<100;i++)
   for (j=0;j<100;j++)
    total+=nprof[i][j];
  fprintf(stdout,"Got %d of em\n",total);
  assert(total==NMOV);
  }
  fclose(starter);
  i=0;
  for (int xi=0;xi<100;xi++)
   for (int xj=0;xj<100;xj++){
     double xeven=fmod(1.*xj,2.);
     double yeven=fmod(1.*xi,2.);
     if (xeven == yeven)
       eo=1;
     else
       eo=0;
     nincol=nprof[xi][xj];
     basex=xi*PDIAM+PDIAM/2.;
     basey=xj*PDIAM+PDIAM/2.;
     for (pz=0;pz<nincol;pz++){
      if ((xi != 0) && (xi != 99))
       p[i].loc.x=basex+.2*(drand48()-0.5); 
      else
       if (xi == 0)
        p[i].loc.x=basex+(.1*drand48()+PDISP);
       else
        p[i].loc.x=basex-(.1*drand48()+PDISP);
      if ((xj != 0) && (xj != 99)) 
       p[i].loc.y=basey+.2*(drand48()-0.5); 
      else
       if (xj == 0)
        p[i].loc.y=basey+(.1*drand48()+PDISP);
       else
        p[i].loc.y=basey-(.1*drand48()+PDISP);
      p[i].diam = PDIAM * (1. + 2. * PDISP * (drand48() - .5) );
      p[i].loc.z=1.5*(1+pz)+TheParams->Ampl+0.1+.75*PDIAM*eo;
      p[i].vel.x=.01*(drand48()-0.5);
      p[i].vel.y=.01*(drand48()-0.5);
      p[i].vel.z=.01*(drand48()-0.5);
      p[i].ome.x=0;
      p[i].ome.y=0;
      p[i].ome.z=0;
      p[i].time=Stime;
      p[i].g=G;
      p[i].cl = NULL;
      p[i].pty = SPHERE;
      xcell = p[i].cell.x = (int) p[i].loc.x + 1;
      ycell = p[i].cell.y = (int) p[i].loc.y + 1;
      zcell = p[i].cell.z = (int) p[i].loc.z + 1;
      TheGrid[xcell][ycell][zcell].add(i);             
      assert(p[i].loc.x-p[i].diam/2.>0);
      assert(p[i].loc.x+p[i].diam/2.<XBSIZE);
      assert(p[i].loc.y-p[i].diam/2.>0);
      if (p[i].loc.y + p[i].diam/2.> YBSIZE){
       fprintf(stdout,"i:%i basey: %f y: %f diam: %f xj:%i\n",i,basey,p[i].loc.y,p[i].diam,xj);
   }
      assert(p[i].loc.y+p[i].diam/2.<YBSIZE);
      i++; 
     }
   }
  
  fprintf(stdout,"Done with the mugs\n");

#endif
#endif
 
#if PERIODIC
 for (i=TheParams->fball;i<=TheParams->lball;++i){
  deltaT=Gtime-p[i].time;

#if DIMENSION ==3
  tempx=p[i].loc.x+deltaT*p[i].vel.x;

  if (tempx > XBSIZE) {
    tempx-=XBSIZE;
    evolve(i,Gtime,0);
   } /*Tempx > XBS*/

  if (tempx < 0) {
    tempx+=XBSIZE;
    evolve(i,Gtime,0);
  } /*Tempx < 0*/

  startx[i]=tempx;
  numroundx[i]=0;
#endif/*DIM == 3*/

#if PERIODIC != 2
  tempy=p[i].loc.y+deltaT*p[i].vel.y;

  if (tempy > YBSIZE) {
    tempy-=YBSIZE;
    evolve(i,Gtime,0);
  }/*tempy >  YBSIZE*/

  if (tempy < 0) {
    tempy+=YBSIZE;
    evolve(i,Gtime,0);
  } /*tempy < 0*/

  starty[i]=tempy;
  numroundy[i]=0;
#endif/*PERIODIC == 1*/
#if PERIODIC == 3
  tempz=p[i].loc.z+deltaT*p[i].vel.z;

  if (tempz > ZBSIZE) {
    tempz-=ZBSIZE;
    evolve(i,Gtime,0);
  }/*tempz >  ZBSIZE*/

  if (tempz < 0) {
    tempz+=ZBSIZE;
    evolve(i,Gtime,0);
  } /*tempz < 0*/

  startz[i]=tempz;
  numroundz[i]=0;
#endif
 }
#endif/*PERIODIC*/

#if MEASUREP==1
 for (i=TheParams->fball;i<=TheParams->lball;++i){
  lastx[i]=p[i].loc.y;
  numcross[i]=0;
}
#if START==0
 for (i=0;i<PRES;i++){
  pofl[i]=0;
 }
#else if START ==1
  FILE *input;
  strcpy(name,OLDRUN);
  strcat(name,".pofl");
  input=fopen(name,"rb");
  if (input != NULL){
   fprintf(stdout,"Opened. Reading.\n");
   fread(pofl,sizeof(pofl[0]),(int)PRES,input);
   fclose(input);
   fprintf(stdout,"Closed. \n");
  }
  else{
   fprintf(stdout,"couldnt open %s\n",name);
   fprintf(stdout,"Starting from a blank p(l)\n");
   for (i=0;i<PRES;i++){
    pofl[i]=0;
   }
  }

#endif/*START*/
#endif/*MEASUREP*/

 fprintf(stdout,"p[538] in cell %i with y=%f\n",p[538].cell.y,p[538].loc.y);
  for(i=TheParams->fjunk;i<=TheParams->ljunk;i++) {
    p[i].pty = JUNK;
  }
  debug_planes(oldparms);
  for(i=TheParams->fstat;i<=TheParams->lstat;i++) {
    p[i].pty = STAT;
  }

 fprintf(stdout,"p[538] in cell %i with y=%f\n",p[538].cell.y,p[538].loc.y);
  for(i=TheParams->fvwall;i<=TheParams->lvwall;i++) {
    p[i].pty = VWALL;
    p[i].c = 0;
  }
  p[TheParams->lvwall].norm.z = -1.;
  p[TheParams->lvwall-1].norm.z = 1.;

#if THERMAL == 1
 for (i=TheParams->ptherm;i<=TheParams->ntherm;i++){
   p[i].pty = THERM;
 }
 p[TheParams->ntherm].loc.z=INSET;
 p[TheParams->ptherm].loc.z=ZBSIZE-INSET;
#endif

 fprintf(stdout,"p[538] in cell %i with y=%f\n",p[538].cell.y,p[538].loc.y);
  double cellsize=10.1;
  double sensordiam=0.55;
  double sensorx = 3.65;
  double sensory = 1.2;
  radp = sensordiam/10.1/2.*XBSIZE;
  midpx = sensorx/10.1*XBSIZE;
  midpy = sensory/10.1*YBSIZE; 
  leftp=midpx-radp;
  rightp=midpx+radp;
  frontp=midpy-radp;
  backp=midpy+radp;


 fprintf(stdout,"Leaving pl_init\n");
 fprintf(stdout,"p[538] in cell %i with y=%f\n",p[538].cell.y,p[538].loc.y);

#if GK == 1
 for (i=TheParams->fball;i<=TheParams->lball;++i){
      vinit[i]=p[i].vel;
  }
#endif

 #ifdef TONLY
    for (i=0;i<=TheParams->lball;i++){
      slab_add(i);
    }
#endif


}




void pl_recalc() {
  int sum = TheParams->nball + TheParams->nwall + TheParams->nvwall + TheParams->nstat + TheParams->njunk;
  if (sum > NP)
    exit(-sum);
  else {
    TheParams->fball = 0;
    TheParams->lball = TheParams->fball + TheParams->nball - 1;
    TheParams->fwall = TheParams->lball + 1;
    TheParams->lwall = TheParams->fwall + TheParams->nwall - 1;
    TheParams->fvwall = TheParams->lwall + 1;
    TheParams->lvwall = TheParams->fvwall + TheParams->nvwall - 1;
    TheParams->fstat = TheParams->lvwall + 1;
    TheParams->lstat = TheParams->fstat + TheParams->nstat - 1;
    TheParams->fjunk = TheParams->lstat + 1;
    TheParams->ljunk = TheParams->fjunk + TheParams->njunk - 1;
  }
}


/* This creates two infinite, parallel planes at X=0 and X=BSIZE */

void debug_planes(double Old[]) {
  fprintf(stdout,"setting up standard box, %f side length\n",(double) XBSIZE);
  int xcell, ycell, zcell, i, a;
  double ct,xvat[4],oldzpos,deltaT,xatemp,yatemp,zatemp;

  i = TheParams->fwall;
  p[i].norm.x = 1.0;
  p[i].norm.y = 0.0;
  p[i].norm.z = 0.0;
  p[i].loc.x = XBSIZE - WOFFSET;
  p[i].loc.y = 0.0;
  p[i].loc.z = 0.0;
/*  xcell = (int) p[i].loc.x + 1;
  for(ycell=0;ycell<YGSIZE;ycell++)
    for(zcell=0;zcell<ZGSIZE;zcell++) {
      if ((zcell % 3 == 0) && (ycell % 3 == 0)) {
	fprintf(stderr,"*** Adding %d to cell %d,%d,%d.\n",i,xcell,ycell,zcell);
	TheGrid[xcell][ycell][zcell].add(i);
      }
    } */
  p[i].pty = WALL;

  i = TheParams->fwall + 1;
  p[i].norm.x = -1.0;
  p[i].norm.y = 0.0;
  p[i].norm.z = 0.0;
  p[i].loc.x = WOFFSET;
  p[i].loc.y = 0.0;
  p[i].loc.z = 0.0;
/*  xcell = (int) p[i].loc.x + 1;
  for(ycell=0;ycell<YGSIZE;ycell++)
    for(zcell=0;zcell<ZGSIZE;zcell++) {
      if ((zcell % 3 == 0) && (ycell % 3 == 0)) {
	fprintf(stderr,"*** Adding %d to cell %d,%d,%d.\n",i,xcell,ycell,zcell);
	TheGrid[xcell][ycell][zcell].add(i);
      }
    } */
  p[i].pty = WALL;

  i = TheParams->fwall + 2;
  p[i].norm.x = 0.0;
  p[i].norm.y = 1.0;
  p[i].norm.z = 0.0;
  p[i].loc.x = 0.0;
  p[i].loc.y = YBSIZE - WOFFSET;
  p[i].loc.z = 0.0;
/*  ycell = (int) p[i].loc.y + 1;
  for(xcell=0;xcell<XGSIZE;xcell++)
    for(zcell=0;zcell<ZGSIZE;zcell++) {
      if ((zcell % 3 == 0) && (xcell % 3 == 0)) {
	fprintf(stderr,"*** Adding %d to cell %d,%d,%d.\n",i,xcell,ycell,zcell);
	TheGrid[xcell][ycell][zcell].add(i);
      }
    } */
  p[i].pty = WALL;

  i = TheParams->fwall + 3;
  p[i].norm.x = 0.0;
  p[i].norm.y = -1.0;
  p[i].norm.z = 0.0;
  p[i].loc.x = 0.0;
  p[i].loc.y = WOFFSET;
  p[i].loc.z = 0.0;
/*  ycell = (int) p[i].loc.y + 1;
  for(xcell=0;xcell<XGSIZE;xcell++)
    for(zcell=0;zcell<ZGSIZE;zcell++) {
      if ((zcell % 3 == 0) && (xcell % 3 == 0)) {
	fprintf(stderr,"*** Adding %d to cell %d,%d,%d.\n",i,xcell,ycell,zcell);
	TheGrid[xcell][ycell][zcell].add(i);
      }
    } */
  p[i].pty = WALL;

  i = TheParams->fwall + 4;
  p[i].norm.x = 0.0;
  p[i].norm.y = 0.0;
  p[i].norm.z = 1.0;
  p[i].loc.x = 0.0;
  p[i].loc.y = 0.0;
#ifdef WZOFFSET
  p[i].loc.z = ZBSIZE - WZOFFSET; 
#else 
  p[i].loc.z = ZBSIZE - WOFFSET; 
#endif
/*  zcell = (int) p[i].loc.z + 1;
  for(xcell=0;xcell<(XGSIZE);xcell++)
    for(ycell=0;ycell<(YGSIZE);ycell++) {
      if ((ycell % 3 == 0) && (xcell % 3 == 0)) {
	fprintf(stderr,"*** Adding %d to cell %d,%d,%d.\n",i,xcell,ycell,zcell);
	TheGrid[xcell][ycell][zcell].add(i);
      }
    } */
  p[i].pty = WALL;

  i = TheParams->fwall+5;
  fprintf(stdout,"setting bottom wall\n");
  p[i].norm.x = 0.0;
  p[i].norm.y = 0.0;
  p[i].norm.z = -1.0;
  p[i].loc.x = 0.0;
  p[i].loc.y = 0.0;
/*Use the following two lines if you want a triangle bottom:
  p[i].loc.z = WOFFSET;
  p[i].vel.z = 4. * TheParams->Ampl / TheParams->Period;
  p[i].g = 0.;
*/
//#if START == 0
/*Use the following lines for a parabolic bottom:*/
  p[i].loc.z = WOFFSET + TheParams->Ampl;
#if GAMMASWEEP == 0 
//  p[i].vel.z = GAMMA*TheParams->Period/4.;
  p[i].vel.z = TheParams->Ampl*TheParams->Omega;
  p[i].g = GAMMA;
#else if GAMMASWEEP == 1
  p[i].loc.z = WOFFSET + (GAMMA/(OMEGA*OMEGA));
  p[i].vel.z = GAMMAINIT*TheParams->Period/4.;
  p[i].g = GAMMAINIT;
#endif
#if START == 1
//#else
  fread(xvat,sizeof(xvat),1,starter); 
  fprintf(stdout,"Old Gamma: %f\tOld Freq: %f \n",Old[1],Old[2]);
  fprintf(stdout,"Read xvat from starter\n");


  /* double np=rint(2*xvat[3]*Old[2]);

  fprintf(stdout,"We've gone through %g half-periods\n",np);
  fprintf(stdout,"vel and g should pos and neg and I should reverse them\n");
  fprintf(stdout,"vel: %f  g: %f\n",p[i].vel.z,p[i].g);

  if (fmod(np,2.)){
    fprintf(stdout,"Reversing\n");
    p[i].vel.z *= -1;
    p[i].g *= -1;
  }
*/

#if PLATEMOVE == 0
  p[i].loc.z=Old[1]/Old[2]/Old[2]/32.+WOFFSET;
#else if PLATEMOVE == 1
//  oldzpos = Old[1]/Old[2]/Old[2]/(4.*PI*PI);
#if GAMMASWEEP == 0
  double fixitA = TheParams->Ampl;
#else 
  double fixitA = p[i].loc.z;
#endif  
  oldzpos = xvat[0]-WOFFSET;
  if (oldzpos == fixitA) {
    p[i].loc.z = oldzpos + WOFFSET;
    fprintf(stdout,"No change in Plate position\n");} 
  else{
    fprintf(stdout,"Changing equilibrium position of plate, and adjusting ball height accordingly\n");
    fprintf(stdout,"new A: %f,  oldA: %f\n",fixitA,oldzpos);
    fprintf(stdout,"xvat: %f %f %f %f\n",xvat[0],xvat[1],xvat[2],xvat[3]);
    fprintf(stdout,"Raising everything by %g\n",fixitA - oldzpos);
    fprintf(stdout,"TheParams->Ampl: %f\n",TheParams->Ampl);
    p[i].loc.z = fixitA + WOFFSET;
    fprintf(stdout,"New plate eq. position: %f\n",p[i].loc.z);
    for (a=TheParams->fball;a<=TheParams->lball;++a){
       deltaT=Gtime - p[a].time;
       xatemp = p[a].loc.x + p[a].vel.x * deltaT;
       yatemp = p[a].loc.y + p[a].vel.y * deltaT;
       p[a].loc.z += (fixitA - oldzpos); 
       zatemp = p[a].loc.z + p[a].vel.z * deltaT - 0.5*p[a].g*deltaT*deltaT;
       TheGrid[p[a].cell.x][p[a].cell.y][p[a].cell.z].remove(a);
#if PERIODIC

#if DIMENSION == 3
      if (xatemp > XBSIZE)
       xatemp-= XBSIZE;
      if (xatemp < 0.)
       xatemp+= XBSIZE;
#endif /*DIM == 3*/

#if PERIODIC != 2
      if (yatemp > YBSIZE){
       yatemp-= YBSIZE;
#if MEASUREP == 1
       numcross[a]+=1;
#endif/MEP == 1*/
      }
      if (yatemp < 0.){
       yatemp+= YBSIZE;
#if MEASUREP == 1
       numcross[a]-=1;
#endif /*MP == 1*/
      }
#endif /*PER == 1*/

#if PERIODIC == 3
      if (zatemp > ZBSIZE)
       zatemp-= ZBSIZE;
      if (zatemp < 0.)
       zatemp+= ZBSIZE;
#endif

#endif /*PER*/

       p[a].cell.x = (int)xatemp+1;
       p[a].cell.y = (int)yatemp+1;
       p[a].cell.z = (int)zatemp+1;
       TheGrid[p[a].cell.x][p[a].cell.y][p[a].cell.z].add(a);
     }
    }
#endif
//  p[i].vel.z=xvat[1];
//  p[i].g=xvat[2];
  p[i].time=Stime;
  fclose(starter);
  fprintf(stdout,"Used starter to set position\n");
  fprintf(stdout,"Used the sort of normal velocity and accel for starting\n");
  fprintf(stdout,"Position:%f\t\tTime:%f\n",p[i].loc.z,p[i].time);
  fprintf(stdout,"And set plate time to Gtime\n");
  fprintf(stdout,"Velocity: %f\t\tAcceleration:%f\n",TheParams->WallVel,p[i].g);
#endif

/*From here on is for any bottom*/
  fprintf(stdout,"Going to set cell\n");
  fprintf(stdout,"p[i].loc.z:%f\n",p[i].loc.z);
  fprintf(stdout,"cell: %f\n",ceil(p[i].loc.z));
  fprintf(stdout,"intcell: %i\n",(int)ceil(p[i].loc.z));
  p[i].cell.z = (int)ceil(p[i].loc.z);
  fprintf(stdout,"cell = %i\n",p[i].cell.z);
  fprintf(stdout,"Set  wall's cell\n");
/*  zcell = (int) p[i].loc.z + 1;
  for(xcell=0;xcell<(XGSIZE);xcell++)
    for(ycell=0;ycell<(YGSIZE);ycell++) {
      if ((ycell % 3 == 0) && (xcell % 3 == 0)) {
	TheGrid[xcell][ycell][zcell].add(i);
	fprintf(stderr,"*** Adding %d to cell %d,%d,%d.\n",i,xcell,ycell,zcell);
      }
    } */
  p[i].pty = WALL;
  p[i].diam = 0.;
  fprintf(stdout,"Set wall's pty and diam\n");
/* Get Bottom-Vwall collisions:*/
/* For Triangle: or use the line below (zdetect)
   ct=p[TheParams->lwall].time + (p[TheParams->lwall].cell.z - p[TheParams->lwall].loc.z)/p[TheParams->lwall].vel.z;
*/
  fprintf(stdout,"Screw Virtual Wall Collision:\n");
/* For Parabolic: (both?)*/
//   if (TheParams->Ampl != 0.){
//    ct = zdetect(TheParams->lwall,TheParams->lvwall-1); 
//    printf("Wall- Virtual Wall collision detected at: %f\n",ct);
//    if (ct > Gtime){
//      c_add(TheParams->lwall,TheParams->lvwall-1,ct);
//      printf("Collision added\n");
//      }
//}
 fprintf(stdout,"Leaving debug_planes()\n");
}


void pl_print() {
  int i;
    printf("\n                *** INITIAL PARTICLE LOCATIONS AND VELOCITIES ***\n\n");
  cout << "Gtime = " << Gtime << endl;
  printf("%-4s%24s%8s%24s\n","i","location [x,y,z]"," ","velocity [x,y,z]");
  printf("%-4s%24s%8s%8f\n","type","normal [x,y,z]"," ","ptime");
  printf("%70s\n"," ",SEP70);
  for(i=0;i<NP;++i) {
    printf("%-4d  [ %4.2f,%4.2f,%4.2f ]   [ %4.2f,%4.2f,%4.2f ]",i,p[i].loc.x,p[i].loc.y,p[i].loc.z,p[i].vel.x,p[i].vel.y,p[i].vel.z);
    cout << "  " << p[i].cl << endl; 
    pty_print(i);
    printf("  [ %4.2f,%4.2f,%4.2f ] %f\n\n",p[i].norm.x,p[i].norm.y,p[i].norm.z,p[i].time);
  }
  printf("fball %d, nball %d, lball %d\n",TheParams->fball,TheParams->nball,TheParams->nball);
}


/* p_print( int a ) -- prints info for a */
void p_print( int a ) {
    fprintf(stderr,"%-4d  [ %4.2f,%4.2f,%4.2f ]   [ %4.2f,%4.2f,%4.2f ]\n\n",a,p[a].loc.x,p[a].loc.y,p[a].loc.z,p[a].vel.x,p[a].vel.y,p[a].vel.z);
}

void pty_print(int i) {
  switch (p[i].pty) {
  case SPHERE:
    cout << " sphere ";
    break;
  case WALL:
    cout << " wall ";
    break;
  case VWALL:
    cout << " vwall ";
    break;
  case STAT:
    cout << " stat ";
    break;
  case JUNK:
    cout << " junk ";
    break;
  }
}

/* validate() examines the current particle positions and prints out particle
paris to stderr that are less than on diameter apart.  It also returns a
value of -1 if any such pairs are found.  If no particles are found to 
overlap, 0 is returned */

int validate(int i) {
	int j;
	double distance;
//	fprintf(stderr,"VALIDATING particles\n");
	for(j=0;j<TheParams->nball;j++) 
	  if (i != j) { 
	    distance = sqrt(pow((p[i].loc.x - p[j].loc.x),2) + pow((p[i].loc.y - p[j].loc.y),2));
	    if (distance < TheParams->pdiam) {
//	      if (TheParams->StopOnError)
//	         TheParams->DoSimulate = 0;
   //           fprintf(stderr,"INVALID COLLISION %d and %d at %5.3f sec!!!\n",i,j,Gtime);
              return(0);
	    }
          }
        return(1);
}

#ifdef TONLY
void slab_add(int a){
   int toaddto=p[a].cell.z;
   TheSlabs[toaddto].vzbar = (TheSlabs[toaddto].numin*TheSlabs[toaddto].vzbar+p[a].vel.z)/(1.*(TheSlabs[toaddto].numin+1));
   TheSlabs[toaddto].numin += 1;
}
void slab_remove(int a){
   int totakeout=p[a].cell.z;
   if (TheSlabs[totakeout].numin == 1)
     TheSlabs[totakeout].vzbar=0;
   else
     TheSlabs[totakeout].vzbar = (TheSlabs[totakeout].numin*TheSlabs[totakeout].vzbar-p[a].vel.z)/(1.*(TheSlabs[totakeout].numin-1));
   TheSlabs[totakeout].numin -= 1;
}
#endif
