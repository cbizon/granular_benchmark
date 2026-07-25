#include "main.h"
#include "math.h"
#include "clist.h"
#include "fel.h"
#include "cell.h"
#include "detect.h"
#include "files.h"
#include <stdio.h>
#include <iostream>
using namespace std;
#include <stdlib.h>

extern P_DATA p[];
extern double Gtime;
extern double TimeStep;
extern int fel[];
extern CellSet TheGrid[XGSIZE][YGSIZE][ZGSIZE];
extern int TheNeighbors[NP],
           lastA,
           lastB;
extern ParamStructPtr TheParams;

static inline int grid_cell_exists(int x, int y, int z) {
  return x >= 0 && x < XGSIZE
      && y >= 0 && y < YGSIZE
      && z >= 0 && z < ZGSIZE;
}

/* cl_calc()
*/

void cl_calc( int debug ) {
  double t_c = 0.0;   /* time of collision */
  int i,j,checked=0;
  for(i=TheParams->fball;i<=TheParams->lball;++i) {
    if (debug)
      c_calc(i,1);
    else
      c_calc(i,0);
    //fprintf(stdout,"Calculated collisions for %d\n",i);
  }
  //fprintf(stdout,"Ball collisions calculated\n");
  /*By not calculating collisions of bottom to begin, remove double collisions
    cw_calc(0);*/
  c_add(TheParams->fstat,TheParams->fstat,Gtime + TimeStep);
  c_add(TheParams->fstat + 1,TheParams->fstat + 1,Gtime + TheParams->Period/2.);
  c_add(TheParams->fstat + 2,TheParams->fstat + 2,Gtime + TheParams->Period/FIELDS); 
#if MEASUREP == 1
  c_add(TheParams->fstat + 3,TheParams->fstat + 3,Gtime + TheParams->Period/MPF); 
#endif
}

void c_calc(int a, int debug) {
  double ct;
  int NumNeighbors,i,x,y,z,xcell,ycell,zcell;
  int xc,yc,zc;
  xcell=p[a].cell.x;
  ycell=p[a].cell.y;
  zcell=p[a].cell.z;
  for(x=-1;x<2;x++) {
     xc=xcell+x;
     #if PERIODIC
     #if DIMENSION ==3
        if (xc == 0)
           xc=XBSIZE;
        if (xc > XBSIZE)
           xc=1;
      #endif /*DIM == 3*/
      #endif /*PERIODIC*/
    for(y=-1;y<2;y++) {
       yc=ycell+y;
       #if PERIODIC != 2 && PERIODIC !=0
        if (yc == 0)
           yc=YBSIZE;
        if (yc > YBSIZE)
           yc=1;
       #endif /*PERIODIC IN Y*/
      for(z=-1;z<2;z++) {
       zc=zcell+z;
       #if PERIODIC == 3
        if (zc == 0)
           zc=ZBSIZE;
        if (zc > ZBSIZE)
           zc=1;
       #endif /*PERIODIC in Z*/
        if (!grid_cell_exists(xc,yc,zc))
          continue;
	NumNeighbors = TheGrid[xc][yc][zc].members(TheNeighbors);
        if (NumNeighbors == -99 ){
          fprintf(stdout,"Death in c_calc: %d, %d, %d\n",xcell+x,ycell+y,zcell+z);
          bomb(5,a); }
	for(i=0;i<NumNeighbors;i++) {
          if (a != TheNeighbors[i]){
	    ct = c3detect(a,TheNeighbors[i]);
	    if (ct > Gtime) {
	      c_add(a,TheNeighbors[i],ct);
	    }
	  }
	}
      }
      }
     }
  

  double min = HUGE;
  int minb = -1;

#ifdef GRAVDIM

#if DIMENSION == 3
  for (i=TheParams->fvwall;i<TheParams->lvwall-1;i++){
#else
  for (i=TheParams->fvwall+2;i<TheParams->lvwall-1;i++){
#endif
  ct=vdetect(a,i);
  if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = i;
  }
 }
#else

#if DIMENSION == 3

  if (p[a].vel.x >0.) 
     i=TheParams->fvwall;
  else
     i=TheParams->fvwall+1;
  ct=vdetect(a,i);
  if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = i;
  }
#endif
  
  if (p[a].vel.y >0. )
     i=TheParams->fvwall+2;
  else
     i=TheParams->fvwall+3;
  ct=vdetect(a,i);
  if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = i;
  } 
#endif

  ct=vdetect(a,TheParams->lvwall);
  if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = TheParams->lvwall;
  }  

#ifdef GRAVDIM
  if (p[a].vel.z > 0. || p[a].g < 0.){
#else
  if (p[a].vel.z > 0.){
#endif
     ct=vdetect(a,TheParams->lvwall-1);
     if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = TheParams->lvwall-1;
      }  
   }


  if ((minb > -1) && (min > Gtime)) 
    c_add(a,minb,min);

#if THERMAL == 1
    minb = -1;
    min = HUGE;
  ct=vdetect(a,TheParams->ntherm);
  if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = TheParams->ntherm;
  }  

   ct=vdetect(a,TheParams->ptherm);
   if ((ct <= min) && (ct > 0)) {
    min = ct;
    minb = TheParams->ptherm;
   }  

  if ((minb > -1) && (min > Gtime)) 
    c_add(a,minb,min);
#endif /*THERMAL == 1*/

#if PERIODIC != 3
    minb = -1;
    min = HUGE;
#if PERIODIC == 1 
    for(i=TheParams->lwall-1;i<=TheParams->lwall-1;i++) {
#else /*PER != 1*/
#if PERIODIC == 2
    for(i=TheParams->lwall-3;i<=TheParams->lwall-1;i++) {
#else /*PER != 2*/
    for(i=TheParams->fwall;i<=TheParams->lwall-1;i++) {
#endif /*PER == 2*/
#endif /*PER == 1*/
      ct = cwdetect(a,i);
      if ((ct <= min) && (ct > Gtime)) {
	min = ct;
	minb = i;
      }
    }
    
    if (minb > -1) {
      c_add(a,minb,min);
    }

    ct=cwdetect(a,TheParams->lwall);
    if (ct > Gtime){
      c_add(a,TheParams->lwall,ct);
      }
#endif /*PER != 3*/


}

/*cw_calc: builds collision list for the moving wall*/
void cw_calc(int debug){   
  double ct;
  printf("Calculating Bottom collisions at %f\n",Gtime);
  int NumNeighbors,i,x,y,z;
  for(x=1;x<=XBSIZE;x++)
    for(y=1;y<=YBSIZE;y++){
      for(z=p[TheParams->fwall+5].cell.z;z<=ZBSIZE ;z++){
      NumNeighbors=TheGrid[x][y][z].members(TheNeighbors);
      if (NumNeighbors == -99) {
          fprintf(stdout,"Death in cw_calc: %d, %d, %d\n",x,y,z);
          bomb(6,TheParams->lwall); } 
      for(i=0;i<NumNeighbors;i++){
	ct=cwdetect(TheNeighbors[i],TheParams->fwall+5);
#if FOLLOW == 1
        if (TheNeighbors[i] == THIS) 
          fprintf(stdout,"Found a collision between bottom and THIS at %f \n",ct);
#endif
	if (ct > Gtime){ 
	  c_add(TheParams->fwall+5,TheNeighbors[i],ct);
#if FOLLOW == 1
          if (TheNeighbors[i] == THIS)
          fprintf(stdout,"and added it\n");
#endif
          }
//        printf("The particle being checked is %i\n",TheNeighbors[i]);
//        printf("x: %i y: %i z: %i\n",x,y,z);
      }
    }
    }
/*  if (p[TheParams->fwall+5].vel.z > 0){
    ct=p[TheParams->lwall].time + (p[TheParams->lwall].cell.z - p[TheParams->lwall].loc.z)/p[TheParams->lwall].vel.z;
//    printf("Wall- Virtual Wall collision detected at: %f\n",ct);
    if (ct > Gtime){
      c_add(TheParams->lwall,TheParams->lvwall-1,ct);
//      printf("Collision added\n");
      }
  }
  if (p[TheParams->lwall].vel.z < 0){
    ct=p[TheParams->lwall].time + (p[TheParams->lwall].cell.z - 1. - p[TheParams->lwall].loc.z)/p[TheParams->lwall].vel.z;
    if (ct > Gtime)
      c_add(TheParams->lwall,TheParams->lvwall,ct);
      }*/

//really, don't care when we change cells with plate (I hope)
/*  ct=zdetect(TheParams->lwall,TheParams->lvwall-1);
  if (ct > Gtime){
    printf("Added upper collision %f\n",ct); 
    c_add(TheParams->lwall,TheParams->lvwall-1,ct);}
  ct=zdetect(TheParams->lwall,TheParams->lvwall);
  if (ct > Gtime){
    printf("Added lower collision %f\n",ct);
    c_add(TheParams->lwall,TheParams->lvwall,ct);}*/
}

void cv_calc(int a, int b, int debug) {
  double ct;
  int NumNeighbors,i,x,y,z,xcell,ycell,zcell;
  int xc,yc,zc,chec=0;
  xcell=p[a].cell.x;
  ycell=p[a].cell.y;
  zcell=p[a].cell.z;
//  printf("pos xcell=%i yc=%i zc=%i\n",xcell,ycell,zcell);
  ct = Gtime-p[a].time;
//  printf("pos z position is %f\n",p[a].loc.z + p[a].vel.z*ct - 0.5*TheParams->// g
//*ct*ct);
  if (b == TheParams->plusx) {
   for(x=0;x<2;x++)
    for(y=-1;y<2;y++)
      for(z=-1;z<2;z++) {
        xc=xcell+x;
        yc=ycell+y;
        zc=zcell+z;
#if PERIODIC
#if DIMENSION ==3
        if (xc == 0)
           xc=XBSIZE;
        if (xc > XBSIZE)
           xc=1;
#endif
#if PERIODIC != 2
        if (yc == 0)
           yc=YBSIZE;
        if (yc > YBSIZE)
           yc=1;
#endif
#if PERIODIC == 3
        if (zc == 0)
           zc=ZBSIZE;
        if (zc > ZBSIZE)
           zc=1;
#endif
#endif
        if (!grid_cell_exists(xc,yc,zc))
          continue;
	NumNeighbors = TheGrid[xc][yc][zc].members(TheNeighbors);
        if (NumNeighbors == -99 ){
          fprintf(stdout,"1 Death in cv_calc: %d, %d, %d\n",xcell+x,ycell+y,zcell+z);
          bomb(7,a); } 
	for(i=0;i<NumNeighbors;i++) {
          if (a != TheNeighbors[i]){
	   ct = c3detect(a,TheNeighbors[i]);
	  if (ct >= Gtime)
	    c_add(a,TheNeighbors[i],ct);
          }
	}
      }
  }
  if (b == TheParams->negx) {
   for(x=-1;x<1;x++)
    for(y=-1;y<2;y++)
      for(z=-1;z<2;z++) {
        xc=xcell+x;
        yc=ycell+y;
        zc=zcell+z;
#if PERIODIC
#if DIMENSION ==3
        if (xc == 0)
           xc=XBSIZE;
        if (xc > XBSIZE)
           xc=1;
#endif
#if PERIODIC != 2
        if (yc == 0)
           yc=YBSIZE;
        if (yc > YBSIZE)
           yc=1;
#endif
#if PERIODIC == 3
        if (zc == 0)
           zc=ZBSIZE;
        if (zc > ZBSIZE)
           zc=1;
#endif
#endif
        if (!grid_cell_exists(xc,yc,zc))
          continue;
	NumNeighbors = TheGrid[xc][yc][zc].members(TheNeighbors);
        if (NumNeighbors == -99){
          fprintf(stdout,"2 Death in cv_calc: %d, %d, %d\n",xcell+x,ycell+y,zcell+z);
          bomb(7,a);}
	for(i=0;i<NumNeighbors;i++) {
          if (a != TheNeighbors[i]){
	    ct = c3detect(a,TheNeighbors[i]);
	    if (ct >= Gtime)
	     c_add(a,TheNeighbors[i],ct);
	}
       }
      }
  }
  if (b == TheParams->plusy) {
    for(x=-1;x<2;x++)
     for(y=0;y<2;y++)
      for(z=-1;z<2;z++) {
        xc=xcell+x;
        yc=ycell+y;
        zc=zcell+z;
#if PERIODIC
#if DIMENSION ==3
        if (xc == 0)
           xc=XBSIZE;
        if (xc > XBSIZE)
           xc=1;
#endif
#if PERIODIC != 2
        if (yc == 0)
           yc=YBSIZE;
        if (yc > YBSIZE){
           yc=1;
        }
#endif
#if PERIODIC == 3
        if (zc == 0)
           zc=ZBSIZE;
        if (zc > ZBSIZE){
           zc=1;
        }
#endif
#endif
        if (!grid_cell_exists(xc,yc,zc))
          continue;
	NumNeighbors = TheGrid[xc][yc][zc].members(TheNeighbors);
    /*   if (chec)
           fprintf(stdout,"found %i neighbors in %i %i %i\n",NumNeighbors,xc,yc,zc);
*/
        if (NumNeighbors == -99){
          fprintf(stdout,"3 Death in cv_calc: %d %d %d\n",xcell+x,ycell+y,zcell+z);
          bomb(7,a);}
	for(i=0;i<NumNeighbors;i++) {
          if (a != TheNeighbors[i]){
	   ct = c3detect(a,TheNeighbors[i]);
	  if (ct >= Gtime)
	    c_add(a,TheNeighbors[i],ct);}
	}
      }
  }
  if (b == TheParams->negy) {
    for(x=-1;x<2;x++)
     for(y=-1;y<1;y++)
      for(z=-1;z<2;z++) {
        xc=xcell+x;
        yc=ycell+y;
        zc=zcell+z;
#if PERIODIC
#if DIMENSION ==3
        if (xc == 0){
           xc=XBSIZE;
        /*fprintf(stdout,"%i is moving across and checkin his neighbors\n",a);
          chec=1;*/
          }
        if (xc > XBSIZE)
           xc=1;
#endif /*DIM == 3*/
#if PERIODIC != 2
        if (yc == 0){
           yc=YBSIZE;
        }
        if (yc > YBSIZE)
           yc=1;
#endif/*PERIODIC != 2*/
#if PERIODIC == 3
        if (zc == 0){
           zc=ZBSIZE;
        }
        if (zc > ZBSIZE)
           zc=1;
#endif /*PERIODIC == 3*/
#endif /*PERIODIC*/
        if (!grid_cell_exists(xc,yc,zc))
          continue;
	NumNeighbors = TheGrid[xc][yc][zc].members(TheNeighbors);
    /*   if (chec)
           fprintf(stdout,"found %i neighbors in %i %i %i\n",NumNeighbors,xc,yc,zc);
*/
        if (NumNeighbors == -99){
          fprintf(stdout,"4 Death in cv_calc: %d %d %d\n",xcell+x,ycell+y,zcell+z);
          fprintf(stdout,"Particle %d in cell %d, %d, %d is causing problems\n",a,xcell,ycell,zcell);
          fprintf(stdout,"Particle escape(uncounted), Gtime=%f\n",Gtime);
          p[a].loc.z = 1.5;
          TheGrid[p[a].cell.x][p[a].cell.y][p[a].cell.z].remove(a);
          fprintf(stdout,"Old z cell:%d\n",p[a].cell.z);
          p[a].cell.z = 2;
          TheGrid[p[a].cell.x][p[a].cell.y][p[a].cell.z].add(a);
          p[a].time=Gtime;  
          }
	for(i=0;i<NumNeighbors;i++) {
          if (a != TheNeighbors[i]){
	   ct = c3detect(a,TheNeighbors[i]);
	  if (ct >= Gtime)
	    c_add(a,TheNeighbors[i],ct);}
	}
      }
  }
  if (b == TheParams->plusz) {
    for(x=-1;x<2;x++)
      for(y=-1;y<2;y++) 
	for(z=0;z<2;z++) {
        xc=xcell+x;
        yc=ycell+y;
        zc=zcell+z;
#if PERIODIC
#if DIMENSION ==3
        if (xc == 0)
           xc=XBSIZE;
        if (xc > XBSIZE)
           xc=1;
#endif
#if PERIODIC != 2
        if (yc == 0)
           yc=YBSIZE;
        if (yc > YBSIZE)
           yc=1;
#endif
#if PERIODIC == 3
        if (zc == 0)
           zc=ZBSIZE;
        if (zc > ZBSIZE)
           zc=1;
#endif
#endif
        if (!grid_cell_exists(xc,yc,zc))
          continue;
	NumNeighbors = TheGrid[xc][yc][zc].members(TheNeighbors);
         if (NumNeighbors == -99){
          fprintf(stdout,"5 Death in cv_calc: %d %d %d\n",xcell+x,ycell+y,zcell+z);
          bomb(7,a);}
	for(i=0;i<NumNeighbors;i++) {
          if (a != TheNeighbors[i]){
	   ct = c3detect(a,TheNeighbors[i]);
	  if (ct >= Gtime)
	    c_add(a,TheNeighbors[i],ct);
            }
	}
      }
  }

  if (b == TheParams->negz) {
#if (DIMENSION == 3 && QUASI != 1)
    for(x=-1;x<2;x++)
#else
    x=0;
#endif
      for(y=-1;y<2;y++)
	for(z=-1;z<1;z++) {
        xc=xcell+x;
        yc=ycell+y;
        zc=zcell+z;
#if PERIODIC
#if DIMENSION ==3
        if (xc == 0)
           xc=XBSIZE;
        if (xc > XBSIZE)
           xc=1;
#endif
#if PERIODIC != 2
        if (yc == 0)
           yc=YBSIZE;
        if (yc > YBSIZE)
           yc=1;
#endif
#if PERIODIC == 3
        if (zc == 0)
           zc=ZBSIZE;
        if (zc > ZBSIZE)
           zc=1;
#endif
#endif
        if (!grid_cell_exists(xc,yc,zc))
          continue;
	NumNeighbors = TheGrid[xc][yc][zc].members(TheNeighbors);
        if (NumNeighbors == -99){
          fprintf(stdout,"6 Death in cv_calc: %d %d %d\n",xcell+x,ycell+y,zcell+z);
          fprintf(stdout,"Particle %d is in cell %d, %d, %d and is screwing stuff up.",a,xcell,ycell,zcell);
          fprintf(stdout,"Particle escape(uncounted), Gtime=%f\n",Gtime);
          p[a].loc.z = 1.5;
          TheGrid[p[a].cell.x][p[a].cell.y][p[a].cell.z].remove(a);
          fprintf(stdout,"Old z cell:%d\n",p[a].cell.z);
          p[a].cell.z = 2;
          TheGrid[p[a].cell.x][p[a].cell.y][p[a].cell.z].add(a); 
          p[a].time=Gtime;
          } 
	for(i=0;i<NumNeighbors;i++) {
          if (a != TheNeighbors[i]){
	   ct = c3detect(a,TheNeighbors[i]);
	  if (ct >= Gtime)
	    c_add(a,TheNeighbors[i],ct);
         }
	}
     }
/*
//	if (zcell - p[TheParams->lwall].cell.z <= 2){
	  ct=cwdetect(a,TheParams->lwall);
	  if (ct > Gtime)
	    c_add(a,TheParams->lwall,ct);
//          if (a == 9)
//            printf("9 hits bottom at: %f\n", ct);
//	}*/
  }

  double min = HUGE;
  int minb = -1;

/*  for(i=TheParams->fvwall;i<=TheParams->lvwall;i++) {
    ct = cdetect(a,i);
    if ((ct <= min) && (ct >= 0)) {
      min = ct;
      minb = i;
    }
  }*/

#ifdef GRAVDIM

#if DIMENSION == 3
  for (i=TheParams->fvwall;i<TheParams->lvwall-1;i++){
#else
  for (i=TheParams->fvwall+2;i<TheParams->lvwall-1;i++){
#endif
  ct=vdetect(a,i);
  if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = i;
  }
 }
#else
#if DIMENSION == 3

  if (p[a].vel.x >0.) 
     i=TheParams->fvwall;
  else
     i=TheParams->fvwall+1;
  ct=vdetect(a,i);
  if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = i;
  }
#endif
  
  if (p[a].vel.y >0. )
     i=TheParams->fvwall+2;
  else
     i=TheParams->fvwall+3;
  ct=vdetect(a,i);
  if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = i;
  } 
#endif

  ct=vdetect(a,TheParams->lvwall);
  if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = TheParams->lvwall;
  }  

#ifdef GRAVDIM
  if (p[a].vel.z > 0. || p[a].g < 0.){
#else
  if (p[a].vel.z > 0.){
#endif
     ct=vdetect(a,TheParams->lvwall-1);
     if ((ct <= min) && (ct > 0)) {
      min = ct;
      minb = TheParams->lvwall-1;
      }  
   }

  if ((minb > -1) && (min >= Gtime))
    c_add(a,minb,min);

}

void cs_calc(int a) {
  if (a == TheParams->fstat)
    c_add(a,a,Gtime + TimeStep);
  else
    if (a == TheParams->fstat + 1)
      c_add(a,a,Gtime + TheParams->Period/2.);
    else     
      if (a == TheParams->fstat+2)
       c_add(a,a,Gtime + TheParams->Period/FIELDS);
#if MEASUREP
      else
        if (a ==  TheParams->fstat+3)
          c_add(a,a,Gtime+TheParams->Period/MPF);
#endif
}


/* cl_print()
*/

void cl_print( void ) {
  printf("void cl_print(): printing current collision list\n"); 
  printf("%-8s%8s%10s%5s%5s%5s\n","part ","event","time","a","b","cb");
  printf("%70s\n",SEP70);
  int j=0;
  for ( int i=0;i<NP;i++) {
    C_DATA *tmp = p[i].cl;
    printf("** %d :\n",i);
    while ( tmp != NULL ) {
    printf("%8s%-8d%10f%5d%5d%5d\n"," ",j++,tmp->time,i,tmp->b,tmp->cb);
    tmp = tmp->cnext;
    }
  }
  printf("void cl_print(): done\n\n");
}

/* c_print() -- prints collision list for a particle */

void c_print( int a ) {
  C_DATA *tmp = p[a].cl;
  int i = 0;
  fprintf(stderr,"\n\nCOLLISION LIST %d\n",a);
  fprintf(stderr,"%-8s%8s%10s%5s%5s%5s\n","part ","event","time","a","b","cb");
  while ( tmp != NULL ) {
    fprintf(stderr,"%8s%-8d%10f%5d%5d%5d\n"," ",i++,tmp->time,a,tmp->b,tmp->cb);
    tmp = tmp->cnext;
  }
}

/* cl_sort
Resorts the collision list
*/

void cl_sort() {
    printf("void cl_sort(): sorting list -- not yet working...\n");
}


/* valid checks to see if the current collision is the same as the last collision,  this has happened occasionally in the past due to round off error problems.  If the current time is 83.33333 and the next collision time is also 83.3333, sometimes the same collision will be added again.  This just checks to see if the two particle colliding were also the last particles to collide.  This makes the assumption that two particles cannot collide twice in succession without hitting other things first.  This *MAY NOT* be acceptable for periodic boundary conditions!!!!!!!!   */

int c_valid(int a, int b) {
/*   if ((lastA == a) && (lastB == b)) {
    fprintf(stderr,"HEY BUDDY!!  You collided last time!\n");
    return(0);  // hey! we have the same collision here, bail out!
  }
  if ((lastB == a) && (lastA == b)) {
    fprintf(stderr,"HEY BUDDY!!  You collided last time!\n");
    return(0);  // hey! we have the same collision here, bail out!
  }
  return(1);  // otherwise we must be OK!
*/

  if (p[a].cl->cb == p[b].c)
    return(1);
  else
    return(0);
}


/* c_add
Adds a collision to a local collision list
*/

void c_add( int a, int b, double t_c ) {

  C_DATA *tmp = (C_DATA *) calloc(1,sizeof(C_DATA));
  if (tmp == NULL) {
    fprintf(stdout,"Death in c_add\n");
    bomb(8,-99);}
  tmp->time = t_c;
  tmp->b = b;
  tmp->cb = p[b].c;
  tmp->cnext = NULL;
  if (p[a].cl == NULL) {
    p[a].cl = tmp;
  }
  else {
    if (tmp->time < p[a].cl->time ) {
      tmp->cnext = p[a].cl;
      p[a].cl = tmp;
    }
    else {
      C_DATA *prev = p[a].cl;
      C_DATA *next = p[a].cl->cnext;
      while ((next != NULL) && (next->time < tmp->time)) {
	next = next->cnext;
	prev = prev->cnext;
      }
      prev->cnext = tmp;
      tmp->cnext = next;
    }
  }
//  if (p[a].pty == SPHERE)
//    fprintf(stderr,"c_add(%d,%d,%f)\n",a,b,t_c);
}

/* returns the particle index for the next valid collision.  If there are no more valid collisions, then it returns -1 */

int GetNextCollision() {
  int a,b,done;
  while (1) {
    a = fel[0];
    if (p[a].cl == NULL) {
      // fprintf(stderr,"*** NO MORE VALID COLLISIONS ***\n");
      return(-1);    /* if no more collisions, return -1 */
    }
    b = p[a].cl->b;
    /* check to see if other particle has suffered a collision */
    if (p[a].cl->cb == p[b].c)
      return(a);  /* collision is still valid */
    else {
      // fprintf(stderr,"*** TIME SUCKER *** FOUND INVALID COLLISION\n");
      c_delete(a);
      fel_sort(0);
    }    
  }
}


/* deletes the first collision from p[a]'s collision list */
void c_delete( int a ) {
  C_DATA *toDelete, *restList;
  restList = p[a].cl->cnext;
  toDelete = p[a].cl;
  p[a].cl = restList;
  free(toDelete);
//  fprintf(stderr,"c_delete: deleted first collision from %d\n",a);
}

//Originally, the if covered to past todel = NULL:, but I am going to
//move it

void destroy_list( C_DATA *todel ) {
  if (todel->cnext != NULL) {
    destroy_list( todel->cnext );}
    free( todel );
    todel = NULL;
 // }
}

void lel_destroy( int a, int debug ) {
  if (p[a].cl != NULL) {
    destroy_list( p[a].cl );
    p[a].cl = NULL;
  }
  if (debug)
    fprintf(stderr,"lel_destroy: just destroyed list %d\n",a);
}

void lel_destroy_all() {
  for(int i=0;i<NP;i++)
    lel_destroy(i,0);
}
