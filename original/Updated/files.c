#include "files.h"
#include <stdlib.h>
#include <iostream>
using namespace std;
#include <stdio.h>
#include <math.h>
#include "main.h"
#include "string.h"

extern double Gtime;
extern P_DATA p[];
extern long NumBallColl;
extern long NumWallColl;
extern ParamStructPtr TheParams;
extern FILE *list,*balls,*stats,*tracks,*pos,*vel,*restart,*starter,*plate,
            *fieldtime,*platevel;
#if COUNTCOLS == 1
extern FILE *numcoll;
#endif /*COUNTCOL == 1*/
#if ROTATIONS == 1
extern FILE *ome;
#endif
#if PERIODIC
extern FILE *crossings;
#endif
#if RESTTYPE == 1
extern double RSLOPEB,RSLOPEW,VMIN;
#endif
#ifdef GRAVDIM 
extern FILE *gs;
#endif

/*Opens output files*/
void open_files() {

  char name[50]; 
 
  strcpy(name,RUN);
  strcat(name,".stats");
  stats=fopen(name,"a");

  strcpy(name,RUN);
  strcat(name,".tracks");
  tracks=fopen(name,"a");
 
  strcpy(name,RUN);
  strcat(name,".pos");
  pos=fopen(name,"a");

  strcpy(name,RUN);
  strcat(name,".vel");
  vel=fopen(name,"a");

#if PERIODIC
  strcpy(name,RUN);
  strcat(name,".cross");
  crossings=fopen(name,"a");
#endif /*PERIODIC == 1*/

#if ROTATIONS == 1
  strcpy(name,RUN);
  strcat(name,".ome");
  ome=fopen(name,"a");
#endif

#if COUNTCOLS == 1
  strcpy(name,RUN);
  strcat(name,".coll");
  numcoll=fopen(name,"a");
#endif

#ifdef GRAVDIM
  strcpy(name,RUN);
  strcat(name,".g");
  gs=fopen(name,"a");
#endif


  strcpy(name,RUN);
  strcat(name,".plate");
  plate=fopen(name,"a");

  strcpy(name,RUN);
  strcat(name,".fieldtime");
  fieldtime=fopen(name,"ab");

  strcpy(name,RUN);
  strcat(name,".platevel");
  platevel=fopen(name,"ab");
}

void close_files()
{
  fclose(stats);
  fclose(tracks);
  fclose(pos);
  fclose(ome);
  fclose(vel);
#if PERIODIC
  fclose(crossings);
#endif
  fclose(plate);
  fclose(fieldtime);
  fclose(platevel);
#ifdef GRAVDIM
  fclose(gs);
#endif
}

void open_stats()
{
  char name[50]; 
 
  strcpy(name,RUN);
  strcat(name,".stats");
  stats=fopen(name,"a");
  strcpy(name,RUN);
  strcat(name,".tracks");
  tracks=fopen(name,"a");
}

void close_stats()
{
  fclose(stats);
  fclose(tracks);
}

void first_write(int check) {

  int i;
  char name[50];
  double mu1,mu2;

  /*Open and Write the .list and .balls files*/
  
  strcpy(name,RUN);
  strcat(name,".list");
  list=fopen(name,"w");

  strcpy(name,RUN);
  strcat(name,".balls");
  balls=fopen(name,"wb");                   
 

  fprintf(list,"**********************************************************\n");
  fprintf(list,"    Welcome to the Newman-Bizon Granular Dynamics Code\n");
  fprintf(list,"**********************************************************\n");
  if (START == 0)
     fprintf(list,"Calculation Started from random grid\n");
  else
     fprintf(list,"Calculation started from %s\n",OLDRUN);
  fprintf(list,"Results stored in %s\n",RUN); 
  fprintf(list,"-----------------------------------------------------------\n");
  fprintf(list,"Number of Particles: %d\n",NMOV);
#if PLATEMOVE == 0
  fprintf(list,"Bottom plate moving parabolically\n");
#else if PLATEMOVE == 1
  fprintf(list,"Bottom plate moving sinusoidally\n");
#endif
#if GAMMASWEEP == 0
  fprintf(list,"Gamma: %f \t\tFrequency: %f\n",GAMMA,FREQUENCY);
#else if GAMMASWEEP == 1
  fprintf(list,"Initial Gamma: %f \t\tFinalGamma: %f\n",GAMMAINIT,GAMMAFINAL);
  fprintf(list,"Gamma changes by: %f  every %i periods\n",GAMMASTEP,GAMMATIME);
#endif
  fprintf(list,"Period: %f \t\tAmplitude: %f\n",PERIOD,AMPL);
  fprintf(list,"Pdiam: %f \t\tPolydispersion: %f\n",PDIAM,PDISP);
  fprintf(list,"----------------------------------------------Restitutions:\n");
#if RESTTYPE == 0
  fprintf(list,"Ball-Ball: %f \t\tBall-Wall: %f\n",BALLREST,WALLREST);
#else if RESTTYPE == 1
  fprintf(list,"Maximum Ball-Ball: %f \tMaximum Ball-Wall: %f\n",BALLREST,WALLREST);
  fprintf(list,"rslopeb: %g \t\trslopew: %g\n",RSLOPEB,RSLOPEW);
  fprintf(list,"Vmin: %g\n",VMIN);
#endif
#if ROTATIONS == 1
  fprintf(list,"----------------------Rotational Coefficient of Restitution\n");
  fprintf(list,"Ball-Ball: %f \t\tBall-Wall: %f\n",TheParams->beta0w,TheParams->beta0b);
#endif
  fprintf(list,"----------------------------------Coefficients of Friction:\n");
#if ((WALLFRICTION == 1) || (WALLFRICTION == 2))
  mu1 = TheParams->wmu;
#else
  mu1 = 0.;
#endif
#if BALLFRICTION == 1
  mu2 = TheParams->bmu;
#else
  mu2 = 0.;
#endif
#if ROTATIONS == 1
  mu1=TheParams->wmu;
  mu2=TheParams->bmu;
#endif
  fprintf(list,"Ball-Ball: %f \t\tBall-Wall: %f\n",mu2,mu1);
  fprintf(list,"-----------------------------------------------------------\n");
  fprintf(list,"Simulation Time (in periods): \t %f\n",1.*TFINAL);
  fprintf(list,"Number of fields per period: \t %f\n",FIELDS);
  fprintf(list,"Number of  stats per period: \t %f\n",STATS);
  fprintf(list,"-----------------------------------------------------------\n");
  fprintf(list,"Number of virtual cells (x): %f\n",1.*XBSIZE);
  fprintf(list,"Number of virtual cells (y): %f\n",1.*YBSIZE);
  fprintf(list,"Number of virtual cells (z): %f\n",1.*ZBSIZE);
  fprintf(list,"Number of Dimensions: %d\n",DIMENSION);
  fprintf(list,"-----------------------------------------------------------\n");
  fprintf(list,"Fields written as ");
#if QFLOATS == 0
  fprintf(list,"Floats\n");
#else 
  fprintf(list,"Doubles\n");
#endif
  fprintf(list,"-----------------------------------------------------------\n");

/*  if (MODE == 0 || MODE == 1)
    fprintf(list,"Discrete Event Code\n");
  if (MODE == 1) 
    fprintf(list,"Alternated with "); 
  if (MODE == 1 || MODE == 2){
    switch (MD){
    case 0:
      fprintf(list,"Verlet Method");
    case 1:
      fprintf(list,"Predictor Corrector");
    case 2: 
      fprintf(list,"Other");
    }
  if (MODE == 1) 
   fprintf(list," only \n");
  if (MODE == 2)
   fprintf(list,"\n");
  }*/
   
  if (check != 0) {
   fprintf(list,"\nThe number of balls differs from that in %s.\n",OLDRUN);
   fprintf(list,"This is quite fatal.\n");
   fprintf(list,"Shutting this run down.\n");
   fclose(list);
   fclose(balls);
   fclose(stats);
   fclose(plate);
   fclose(pos);
   fclose(vel);
   abort();} 

  fclose(list);

  for (i=TheParams->fball;i<=TheParams->lball;i++) 
    fwrite(&p[i].diam,sizeof(p[i].diam),1,balls);
  
  fclose(balls);
  
}

void bomb (int why,int a){
  char name[50];
  FILE *crash;

  last_writes();
 
  strcpy(name,RUN);
  strcat(name,".bug");
  crash=fopen(name,"w");

  fprintf(crash,"Bombing out -- Gtime = %f\n",Gtime);
  fprintf(crash,"Error code: %i\n",why);
  if (a != -99){
    fprintf(crash,"Particle %i has been implicated\n",a);
    fprintf(crash,"Positions-- X:%f, Y:%f, Z:%f\n",p[a].loc.x,p[a].loc.y,p[a].loc.z);
    fprintf(crash,"Velocities-- X:%f, Y:%f, Z:%f\n",p[a].vel.x,p[a].vel.y,p[a].vel.z);
    fprintf(crash,"Cells-- X:%i, Y:%i, Z:%i\n",p[a].cell.x,p[a].cell.y,p[a].cell.z);}
    fprintf(crash,"Particle Time - %f\n",p[a].time);
    fprintf(crash,"Diameter: %f\n",p[a].diam);
    fprintf(crash,"Root Accuracy: %g\n",ROOTACC);
  abort();
}

void write_restart(){

  double dt,xvat[4],out0,out1,out2;
  int i;
  double total;
  char name[50];

  out0=NMOV*1.;
  out1=GAMMA*1.;
  out2=FREQUENCY*1.;

  strcpy(name,RUN);
  strcat(name,".restart"); 
  restart=fopen(name,"wb");

  fwrite(&out0,sizeof(out0),1,restart);
  fwrite(&out1,sizeof(out1),1,restart);
  fwrite(&out2,sizeof(out2),1,restart);
  fwrite(&Gtime,sizeof(Gtime),1,restart);

  for (i=TheParams->fball;i<=TheParams->lball;i++) {
    fwrite(&p[i].diam,sizeof(p[i].diam),1,restart);
    fwrite(&p[i].loc.x,sizeof(p[i].loc.x),1,restart);
    fwrite(&p[i].loc.y,sizeof(p[i].loc.x),1,restart);
    fwrite(&p[i].loc.z,sizeof(p[i].loc.x),1,restart);
    fwrite(&p[i].vel.x,sizeof(p[i].loc.x),1,restart); 
    fwrite(&p[i].vel.y,sizeof(p[i].loc.x),1,restart); 
    fwrite(&p[i].vel.z,sizeof(p[i].loc.x),1,restart);
    fwrite(&p[i].cell.x,sizeof(p[i].cell.x),1,restart);
    fwrite(&p[i].cell.y,sizeof(p[i].cell.y),1,restart);
    fwrite(&p[i].cell.z,sizeof(p[i].cell.z),1,restart);
    fwrite(&p[i].time,sizeof(p[i].time),1,restart);
#ifdef GRAVDIM
    fwrite(&p[i].gvec.x,sizeof(p[i].g),1,restart);
    fwrite(&p[i].gvec.y,sizeof(p[i].g),1,restart);
    fwrite(&p[i].gvec.z,sizeof(p[i].g),1,restart);
#else
    fwrite(&p[i].g,sizeof(p[i].g),1,restart);
#endif
#if ROTATIONS == 1
    fwrite(&p[i].ome.x,sizeof(p[i].loc.x),1,restart); 
    fwrite(&p[i].ome.y,sizeof(p[i].loc.x),1,restart); 
    fwrite(&p[i].ome.z,sizeof(p[i].loc.x),1,restart);
#endif
    
    total += p[i].c; } 


  xvat[0]=p[TheParams->fwall+5].loc.z;
  xvat[1]=p[TheParams->fwall+5].vel.z;
  xvat[2]=p[TheParams->fwall+5].g;
  xvat[3]=p[TheParams->fwall+5].time;

  fwrite(xvat,sizeof(xvat),1,restart);        
  
  fclose(restart);
  
}

void last_writes() {
 
  double dt,xvat[4],out0,out1,out2;
  int i;
  char name[50];
  long total=0;

/*  fclose(stats);
  fclose(tracks);
  fclose(pos);
  fclose(vel);
  fclose(plate);

 #if ROTATIONS == 1
  fclose(ome);
 #endif
 #if COUNTCOLS == 1
  fclose(numcoll);
 #endif
*/

  out0=NMOV*1.;
  out1=GAMMA*1.;
  out2=FREQUENCY*1.;

  strcpy(name,RUN);
  strcat(name,".restart"); 
  restart=fopen(name,"wb");

  fwrite(&out0,sizeof(out0),1,restart);
  fwrite(&out1,sizeof(out1),1,restart);
  fwrite(&out2,sizeof(out2),1,restart);
  fwrite(&Gtime,sizeof(Gtime),1,restart);

  for (i=TheParams->fball;i<=TheParams->lball;i++) {
    fwrite(&p[i].diam,sizeof(p[i].diam),1,restart);
    fwrite(&p[i].loc.x,sizeof(p[i].loc.x),1,restart);
    fwrite(&p[i].loc.y,sizeof(p[i].loc.x),1,restart);
    fwrite(&p[i].loc.z,sizeof(p[i].loc.x),1,restart);
    fwrite(&p[i].vel.x,sizeof(p[i].loc.x),1,restart); 
    fwrite(&p[i].vel.y,sizeof(p[i].loc.x),1,restart); 
    fwrite(&p[i].vel.z,sizeof(p[i].loc.x),1,restart);
    fwrite(&p[i].cell.x,sizeof(p[i].cell.x),1,restart);
    fwrite(&p[i].cell.y,sizeof(p[i].cell.y),1,restart);
    fwrite(&p[i].cell.z,sizeof(p[i].cell.z),1,restart);
    fwrite(&p[i].time,sizeof(p[i].time),1,restart);
    fwrite(&p[i].g,sizeof(p[i].g),1,restart);
#if ROTATIONS == 1
    fwrite(&p[i].ome.x,sizeof(p[i].loc.x),1,restart); 
    fwrite(&p[i].ome.y,sizeof(p[i].loc.x),1,restart); 
    fwrite(&p[i].ome.z,sizeof(p[i].loc.x),1,restart);
#endif
    
    total += p[i].c; } 

  xvat[0]=p[TheParams->fwall+5].loc.z;
  xvat[1]=p[TheParams->fwall+5].vel.z;
  xvat[2]=p[TheParams->fwall+5].g;
  xvat[3]=p[TheParams->fwall+5].time;

  fwrite(xvat,sizeof(xvat),1,restart);        
  
  fclose(restart);
  
  fprintf(stdout,"The total number of collisions/Period is %f\n",(1.*total)/TFINAL);

}

int check_restart() {

  double oldparms[3];
  int value;
  char name[50];


  strcpy(name,OLDRUN);
  strcat(name,".restart");
  starter=fopen(name,"rb");


  fread(&oldparms[0],sizeof(oldparms[0]),1,starter); 
  fread(&oldparms[1],sizeof(oldparms[1]),1,starter); 
  fread(&oldparms[2],sizeof(oldparms[2]),1,starter);

  fclose(starter);

//  printf("%f,%f,%f\n",oldparms[0],oldparms[1],oldparms[2]);
   
  value=0;

  if (oldparms[0] != NMOV)
    value += 100;
// if (oldparms[1] != GAMMA)
//   value += 10;
// if (oldparms[2] != FREQUENCY)
//   value +=1;

//if (oldparms[1]/(oldparms[2]*oldparms[2])+WOFFSET < GAMMA/(FREQUENCY*FREQUENCY))
//    value += 1000;
  
//  if( (GAMMA/(FREQUENCY*FREQUENCY)-oldparms[1]/(oldparms[2]*oldparms[2]))
//    value+=1000; 
 
  fprintf(stdout,"The restart value is %d\n",value); 

//  printf("%g\n",GAMMA/(FREQUENCY*FREQUENCY)-oldparms[1]/(oldparms[2]*oldparms[2]));

  return(value);
}
