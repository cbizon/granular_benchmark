#include "detect.h"
#include "main.h"
#include "files.h"
#include <stdlib.h>
#include <iostream>
using namespace std;
#include <stdio.h>
#include <math.h>
#include <assert.h>

extern P_DATA p[];
extern double Gtime;
extern ParamStructPtr TheParams;
extern double worstdt,worstdz;

/* Determines whether p[a] and p[b] collide in 3D.  First resolves two trajectories into x,y,z component vectors.  Then checks to see if collision occurs in each of three dimensions.  If it fails in any direction, then it bombs out immediately.  If it passes, then a true (time consuming) collision detection routing is run */

/*Also, if both particles have the same vertical acceleration, c3detect is used.Otherwise, a fourth order polynomial must be solved, and c4detect is called.)*/

double cdetect(int a, int b) {
  if ((p[a].pty == SPHERE) && (p[b].pty == SPHERE)) {
#ifdef GRAVDIM
        if (a != b) 
          if (p[a].gvec.x == p[b].gvec.x && p[a].gvec.y == p[b].gvec.z && p[a].g==p[b].g)
            return(c3detect(a,b));  
          else
            return(c4detect(a,b));
        else 
          return(-77.);
#else
        if (a != b) 
            return(c3detect(a,b));  
        else 
          return(-77.);
#endif
  }
  else {
/*    if (p[a].pty == WALL) {
       fprintf(stdout,"Death in cdetect\n");
       assert(p[a].pty != WALL);}*/
    if (p[b].pty == WALL)
       return(cwdetect(a,b));
    else
      return(vdetect(a,b));
  }
}

/* Determines when a sphere and a wall collide.  Returns the type double.  Parameter "a" is the sphere, "w" is the wall */

double cwdetect(int a, int w) {
  double DotProduct,result,fudge,deltaX,deltaY,deltaZ;
  double pr = p[a].diam/2.;

  DotProduct = p[a].vel.x * p[w].norm.x + p[a].vel.y * p[w].norm.y + p[a].vel.z * p[w].norm.z;
  if ((((w == TheParams->fwall + 4)||(w==TheParams->fwall+5)) && (p[a].g != 0)) || ((w == TheParams->fwall + 5) && (PLATEMOVE == 1)) )
    result = zdetect(a,w);
  else
    if (DotProduct > 0)
      result = (p[w].norm.x*(p[w].loc.x-p[a].loc.x) + p[w].norm.y*(p[w].loc.y-p[a].loc.y) + p[w].norm.z*(p[w].loc.z-p[a].loc.z)-pr)/DotProduct + p[a].time;  
    else    
      result = -1.0;
  return(result);
}

#ifdef GRAVDIM
double xydetect(int a, int w) {
#if PERIODIC == 3 || PERIODIC ==2 || PERIODIC == 1
  double dtime=Gtime-p[a].time;
#endif
  double wtf,sb,radical,q,t1,t2,wallr,wallvr;
  double veldiff,gdiff,dt;
  double ballvr;
  double pr,r,wnorm;
  int valid1 = 0;
  int valid2 = 0;
  pr = 0.;
  wallvr=0;
  if (w==TheParams->plusx){
    wallr=(double)p[a].cell.x;
    veldiff=p[a].vel.x-wallvr;
    gdiff = p[a].gvec.x - p[w].g;
    r=p[a].loc.x;
  }
  if (w==TheParams->negx){
    wallr=(double)(p[a].cell.x - 1);
    veldiff=p[a].vel.x-wallvr;
    gdiff = p[a].gvec.x - p[w].g;
    r=p[a].loc.x;
  }
  if (w==TheParams->plusy){
    wallr=(double)p[a].cell.y;
    veldiff=p[a].vel.y-wallvr;
    gdiff = p[a].gvec.y - p[w].g;
    r=p[a].loc.y;
  }
  if (w==TheParams->negy){
    wallr=(double)(p[a].cell.y - 1);
    veldiff=p[a].vel.y-wallvr;
    gdiff = p[a].gvec.y - p[w].g;
    r=p[a].loc.y;
  }

 
  if (veldiff < 0)
    sb=-1.;
  else
    sb=1.;

#if PERIODIC == 1 || PERIODIC == 2 || PERIODIC == 3
 if (w == TheParams->plusx || w==TheParams->negx){
  double newx=p[a].loc.x+p[a].vel.x*dtime-.5*p[a].gvec.x*dtime*dtime;
  if (newx > p[a].cell.x +2)
   wallr+=XBSIZE; 
  if (newx < p[a].cell.x -2)
   wallr-=XBSIZE; 
 }
 if (w == TheParams->plusy || w==TheParams->negy){
  double newy=p[a].loc.y+p[a].vel.y*dtime-.5*p[a].gvec.y*dtime*dtime;
  if (newy > p[a].cell.y +2)
   wallr+=YBSIZE; 
  if (newy < p[a].cell.y -2)
   wallr-=YBSIZE; 
 }
#endif

  radical = veldiff * veldiff - 2. * gdiff * (wallr - r);

  if (radical >= 0) {
    q = -.5*(veldiff+sb*sqrt(radical));
    t1 = -2.*q/gdiff;
    t2 = (r-wallr)/q;
  
 
    t1 += p[a].time;
    t2 += p[a].time;

    if (t2 < t1){
     dt = t1;
     t1=t2;
     t2=dt;}  

   
    dt = t1 - p[a].time;
    if (w == TheParams->plusx || w==TheParams->negx){
     ballvr = p[a].vel.x - p[a].gvec.x * dt;
     wnorm=-1*(w-TheParams->plusx-.5);
    }
    if (w == TheParams->plusy || w==TheParams->negy){
     ballvr = p[a].vel.y - p[a].gvec.y * dt;
     wnorm=-1*(w-TheParams->plusy-.5);
    }
    dt = t1 - p[w].time;
    wallvr = 0;


    if ((ballvr-wallvr)*wnorm >= 0.){    
      valid1 = 1; }
     
    dt = t2 - p[a].time;
    if (w == TheParams->plusx || w==TheParams->negx){
     ballvr = p[a].vel.x - p[a].gvec.x * dt;
    }
    if (w == TheParams->plusy || w==TheParams->negy){
     ballvr = p[a].vel.y - p[a].gvec.y * dt;
    }
    wallvr = 0;
    if ((ballvr-wallvr)*wnorm >= 0.){
      valid2 = 1; }

if ((t1 > Gtime) && (valid1 == 1)){
      return(t1);}
else
  if ((t2 > Gtime) && (valid2 == 1)){
     return(t2);}
  else{
     return(-40);}

   }
  else {
    return(-1);
  }
}
#endif

#if PLATEMOVE == 0 || PLATEMOVE == -1

double zdetect(int a, int w) {
#if PERIODIC ==3
  double dtime=Gtime-p[a].time;
#endif
  double wtf,sb,radical,q,t1,t2,wallz,wallvz;
  double veldiff,gdiff,dt;
  double ballvz;
  double pr;
  int valid1 = 0;
  int valid2 = 0;
  if (w==TheParams->plusz){
    pr = 0.;
    wallvz=0;
    wallz=(double)p[a].cell.z;
}
  if (w==TheParams->negz){
    pr = 0;
    wallvz=0.;
    wallz=(double)(p[a].cell.z - 1);
     }
#if THERMAL2 == 1
  if (w==TheParams->ptherm || w == TheParams->ntherm){
    pr = 0;
    wallvz = 0.;
    wallz=p[w].loc.z;
  }
#endif
  if ((w == TheParams->fwall + 4) || (w == TheParams->fwall + 5)){
    dt = p[a].time-p[w].time;
    wallz=p[w].loc.z + dt*p[w].vel.z - .5 * dt * dt * p[w].g; 
    pr=p[a].diam/2.;
    wallvz=p[w].vel.z - p[w].g * dt;
    }

  veldiff=p[a].vel.z-wallvz;
  gdiff = p[a].g - p[w].g;
 
  if (veldiff < 0)
    sb=-1.;
  else
    sb=1.;

#if PERIODIC == 3
  double newz=p[a].loc.z+p[a].vel.z*dtime-.5*p[a].g*dtime*dtime;
  if (newz > p[a].cell.z +2)
   wallz+=ZBSIZE; 
  if (newz < p[a].cell.z -2)
   wallz-=ZBSIZE; 
#endif

  radical = veldiff * veldiff - 2. * gdiff * (wallz - p[a].loc.z - p[w].norm.z * pr);

  if (radical >= 0) {
    q = -.5*(veldiff+sb*sqrt(radical));
    t1 = -2.*q/gdiff;
    t2 = ((p[a].loc.z + p[w].norm.z * pr)-wallz)/q;
  
 
    t1 += p[a].time;
    t2 += p[a].time;

    if (t2 < t1){
     dt = t1;
     t1=t2;
     t2=dt;}  
   
#if FOLLOW == 1
 if (a == THIS)
  fprintf(stdout,"At Gtime = %f, t1 = %f, t2 = %f\n",Gtime,t1,t2); 
#endif
 
    dt = t1 - p[a].time;
    ballvz = p[a].vel.z - p[a].g * dt;
    dt = t1 - p[w].time;
    wallvz = p[w].vel.z - p[w].g * dt;

    if ((ballvz-wallvz)*p[w].norm.z >= 0.){    
      valid1 = 1; }
     
    dt = t2 - p[a].time;
    ballvz = p[a].vel.z - p[a].g * dt;
    dt = t2 - p[w].time;
    wallvz = p[w].vel.z - p[w].g * dt;
    if ((ballvz-wallvz)*p[w].norm.z >= 0.){
      valid2 = 1; }

if ((t1 > Gtime) && (valid1 == 1)){
      return(t1);}
else
  if ((t2 > Gtime) && (valid2 == 1)){
     return(t2);}
  else{
     return(-40);}

   }
  else {
    return(-1);
  }
}

#else if PLATEMOVE == 1
double zdetect(int a,int w) {
   
  double wallz,arg,ts,tc,wallvz,pr,veldiff,gdiff,sb;
  double radical,q,t1,t2,dt,ballvz,endtime;
  double lbound,rbound,ztemp,wztemp,vo,vl,vr;
  double troot,some,one;
  int coll=0;
  int valid1=0;
  int valid2=0;
  int possible = 0;

  if (a == TheParams->lwall) {
    if (w==TheParams->plusz) {
      fprintf(stdout,"Working on Upper collistion\n");
      wallz=(double)p[a].cell.z;}
    if (w==TheParams->negz) {
      fprintf(stdout,"Working on Lower collistiotona\n");
      wallz=(double)(p[a].cell.z-1);}
    arg=(wallz-p[a].loc.z)/TheParams->Ampl;
    fprintf(stdout,"Wallz:%f, p[a].loc.z: %f\n",wallz,p[a].loc.z);
    fprintf(stdout,"arg: %f, p[a].time: %f\n",arg,p[a].time);
    if ((arg > 1.) || (arg < -1.))
      return(-99.);
    else{
      fprintf(stdout,"Omega:%f\n",TheParams->Omega);
      ts=(1./TheParams->Omega)*asin((wallz-p[a].loc.z)/TheParams->Ampl);
      fprintf(stdout,"ts: %f\n",ts);
      tc=ts+p[a].time;
      fprintf(stdout,"tc-Gtime:%e\n",tc-Gtime);
      if (p[a].g > 0) {
	if (tc > Gtime) 
	  return(tc);
	else
	  return(p[a].time+TheParams->Period/2.-ts);}
      else {
	tc=p[a].time-ts;
	if (tc < Gtime)
	  return(tc);
	else
	  return(p[a].time+ts+TheParams->Period/2.);
      }
    }
  }
  else
    if ((w == TheParams->plusz) || (w == TheParams -> negz) || (w == TheParams->fwall + 4)){
      wallvz = 0;
      if (w==TheParams->plusz){
	pr = 0.;
	wallz=(double)p[a].cell.z;}
      if (w==TheParams->negz){
	pr = 0;
	wallz=(double)(p[a].cell.z - 1);}
      if (w==TheParams->fwall+4){
	wallz=p[w].loc.z;
	pr=p[a].diam/2.;}
      veldiff=p[a].vel.z-wallvz;
      gdiff = p[a].g - p[w].g; 
      one = wallz - p[a].loc.z - p[w].norm.z * pr;

      if (veldiff < 0)
	sb=-1.;
      else
	sb=1.;
      
       radical = veldiff * veldiff - 2. * gdiff * (one);

  if (radical >= 0) {
    q = -.5*(veldiff+sb*sqrt(radical));
    t1 = -2.*q/gdiff;
    t2 = (-1.*one)/q;
    
    
    t1 += p[a].time;
    t2 += p[a].time;
    
    if (t2 < t1){
      dt = t1;
      t1=t2;
      t2=dt;}  
    
#if FOLLOW == 1
    if (a == THIS){
      fprintf(stdout,"At Gtime = %f, t1 = %f, t2 = %f\n",Gtime,t1,t2); 
      fprintf(stdout,"Gtime-t1: %e\n",Gtime-t1);}
#endif
    
//    if (t1 > Gtime){

      dt = t1 - p[a].time;
      ballvz = p[a].vel.z - p[a].g * dt;
      dt = t1 - p[w].time;
      wallvz = p[w].vel.z - p[w].g * dt;
    
      if ((ballvz-wallvz)*p[w].norm.z >= 0.) {    
	      valid1 = 1;
      //  return(t1);
}

#if FOLLOW == 1
else
  if (a == THIS)
    fprintf(stdout,"t1 is bogus\n");
#endif
//}
//   if (t2 > Gtime){

    dt = t2 - p[a].time;
    ballvz = p[a].vel.z - p[a].g * dt;
    dt = t2 - p[w].time;
    wallvz = p[w].vel.z - p[w].g * dt;
    if ((ballvz-wallvz)*p[w].norm.z >= 0.){
//      return(t2);
      valid2 = 1; }
//  }

//    return(-40.);

#if FOLLOW == 1
else
  if (a == THIS)
    fprintf(stdout,"t2 is bogus\n");
#endif  
    
    if ((t1 > Gtime) && (valid1 == 1)){

#if FOLLOW == 1
      if (a == THIS)
	fprintf(stdout,"Returning t1 = %f\n",t1);
#endif 

      return(t1);}
    else
      if ((t2 > Gtime) && (valid2 == 1)){

#if FOLLOW == 1
	if (a == THIS)
	  fprintf(stdout,"Returning t2 = %f\n",t2);
#endif  

	return(t2);}
      else{

#if FOLLOW == 1
	if (a == THIS){
         fprintf(stdout,"Returning Nothing (-40)\n");
	  fprintf(stdout,"valid1: %i valid2: %i\n",valid1,valid2);
	}
#endif
	return(-40);}
  }
  else {
    return(-1);
  }
    }

  else {
/* Logic Check, seems ok:    assert(w == TheParams -> lwall);*/   
    possible = 0;
    wallz=p[w].loc.z;
    if (p[w].g > 0)
      wallz += TheParams->Ampl;
    dt=Gtime - p[a].time;
    if ((p[a].loc.z + p[a].vel.z*dt - 0.5*p[a].g*dt*dt) < wallz+p[a].diam/2.){
      lbound = p[a].time;
      possible = 1;}
    else {
      pr=p[a].diam/2.;
      veldiff=p[a].vel.z;
      gdiff=p[a].g;
      one=wallz - p[a].loc.z - p[w].norm.z * pr;
      
   
      if (veldiff < 0)
	sb=-1.;
      else
	sb=1.;
      
      radical = veldiff * veldiff - 2. * gdiff * one;
      
      if (radical >= 0) {
	q = -.5*(veldiff+sb*sqrt(radical));
	t1 = -2.*q/gdiff;
	t2 = (-1.*one)/q;
	
	
	t1 += p[a].time;
	t2 += p[a].time;

#if FOLLOW == 1
	if (a == THIS)
	  fprintf(stdout,"t1=%f, t2=%f\n",t1,t2);
#endif
	
	if (t2 < t1){
	  dt = t1;
	  t1=t2;
	  t2=dt;}  
	
	dt = t1 - p[a].time;
	ballvz = p[a].vel.z - p[a].g * dt;  
	if (ballvz < 0)
	  valid1 = 1; 
	
	dt = t2 - p[a].time;
	ballvz = p[a].vel.z - p[a].g * dt;
	if (ballvz < 0)
	  valid2 = 1; 
	
	endtime=p[w].time+TheParams->Period/2.;
	
	if ((t1 > Gtime) && (t1 < endtime) && (valid1 == 1)){
	  lbound = t1;
	  possible = 1;
	}
	else
	  if ((t2 > Gtime) && (t2 < endtime) && (valid2 == 1)){
	    lbound=t2;
	    possible=1;}
      }
      else {
	fprintf(stdout,"Things suck in zdetect %i %i %f\n",a,w,Gtime);
	bomb(2,a);
      }
    }
    if (possible == 0) {
#if FOLLOW == 1 
      if (a == THIS){
	fprintf(stdout,"Not Possible:\n");
	fprintf(stdout,"z: %f,v: %f, t:%f\n",p[a].loc.z,p[a].vel.z,p[a].time);
	fprintf(stdout,"t1 \t\t t2 \t endtime \t valid2\n");
	fprintf(stdout,"%f \t %f \t %f \t %i\n",t1,t2,endtime,valid2);
      }
#endif
      return(-40.);}
    else
      //      fprintf(stdout,"Particle %i has a chance to hit bottom\n",a);
    /*Find out when the actual collision time is and return it*/
    if (p[w].g < 0){
      //	fprintf(stdout,"Easy part\n");
      /*Is there a collision?*/
      rbound=p[w].time+TheParams->Period/2.;
      dt=rbound-p[a].time;
      ztemp=p[a].loc.z+p[a].vel.z*dt-0.5*p[a].g*dt*dt;
      if (ztemp > p[a].diam/2.+p[w].loc.z) {
	/*No collision in that interval, so*/
#if FOLLOW == 1
	if (a == THIS)
	  fprintf(stdout,"But no collision\n");
#endif	  
	return(-10.);
      }
      else {
	/*Is a collision in that interval. Find it.*/
	tc=findroot(a,w,lbound,rbound);
#if FOLLOW == 1
	if (a == THIS)
	  fprintf(stdout,"Ok, got collision: %f\n",Gtime);
#endif
	return(tc);
      }
    }
    else{
      /*Hard One.  There can be one collison when g<1, two when g>1 and 
	one more when g<1 again.  Take them in order, since we want the
	first collision.*/
#if FOLLOW == 1
      if (a == THIS){
	fprintf(stdout,"Z-position: %f, Zvel: %f, Time: %f\n",p[a].loc.z,p[a].vel.z,p[a].time);
	fprintf(stdout,"Hard part\n");}
#endif
      /*First interval*/
      rbound=TheParams->TimeOne+p[w].time;
      /*Due to a problem that comes up when decreasing Gamma (and also
        to more explicitly bound the root:*/
        if (p[a].time < p[w].time)
           lbound = p[w].time;
      /*It could be that the particle comes later in the plate cycle, so
	check*/
      if (rbound > lbound){
	dt=rbound-p[a].time;
	ztemp=p[a].loc.z+p[a].vel.z*dt-0.5*p[a].g*dt*dt;
	wztemp=p[w].loc.z+TheParams->Ampl*sin(TheParams->Omega*TheParams->TimeOne);
	if (ztemp < wztemp+p[a].diam/2.){
	  /*Is a root in this interval: Find and return it*/
	  tc=findroot(a,w,lbound,rbound);
	  return(tc);
	  coll=1;
	}
      }
      if (coll == 0) {
	/*There may be 0,1 or 2 collisions when the acceleration of the 
	  plate is more than that of the ball.  Check first for one 
	  collision:*/
#if FOLLOW == 1
	if (a == THIS)
	  fprintf(stdout,"Didn't find collision in part 1, checking 2\n");
#endif
	if (lbound < p[w].time+TheParams->TimeOne)
	  lbound=p[w].time+TheParams->TimeOne;
	rbound=p[w].time+TheParams->Period/2.-TheParams->TimeOne;
#if FOLLOW == 1
	if (a == THIS){
	  fprintf(stdout,"lbound:%f rbound:%f\n",lbound,rbound);}
#endif
	if (rbound > lbound){
	  dt=rbound-p[a].time;
	  ztemp=p[a].loc.z+p[a].vel.z*dt-0.5*p[a].g*dt*dt;
	  wztemp=p[w].loc.z+TheParams->Ampl*sin(TheParams->Omega*TheParams->TimeOne);
#if FOLLOW == 1
	  if (a == THIS){
	    fprintf(stdout,"At t=%f, ztemp=%f, wztemp=%f\n",rbound,ztemp,wztemp);}
#endif
	  if (ztemp < wztemp+p[a].diam/2.){
	    /* Is exactly one root in there: Find and return it*/
	    tc=findroot(a,w,lbound,rbound);
	    //	      fprintf(stdout,"Found a collision (1root):%f\n",tc);
	    return(tc);
	    coll = 1;
	  }
	  else {
	    /*Are either 0 or 2 roots in there.  There can only be 2 roots 
	      in this range if the relative velocity has a root.*/
	    /*The relative velocity is v[a,t=0]-g*t-Acos(omega t)*/
	    /*Where t=0 is p[w].time*/
	    dt=p[w].time-p[a].time;
	    vo=p[a].vel.z-p[a].g*dt;
	    dt=lbound-p[w].time;
	    vl=vo-p[a].g*dt-TheParams->WallVel*cos(TheParams->Omega*dt);
	    dt=rbound-p[w].time;
	    vr=vo-p[a].g*dt-TheParams->WallVel*cos(TheParams->Omega*dt);
#if FOLLOW == 1
	    if (a == THIS){
	      fprintf(stdout,"vl: %f, vr: %f\n",vl,vr);}
#endif
	    if ((vl*vr) < 0.){
	      /*The relative velocity has a root, so there may be 2 roots
		in the position. Need to get the position of the root.*/
	      troot=findvroot(a,w,lbound,rbound);
              if (troot == -456.){
 	        fprintf(stdout,"vl: %f, vr: %f\n",vl,vr);
                bomb(1,0);
              }
#if FOLLOW == 1
	      if (a == THIS){
		fprintf(stdout,"troot: %f\n",troot);}
#endif		
	      /*Now, is there a root of the position between lbound and 
		troot?*/
	      dt=troot-p[a].time;
	      ztemp=p[a].loc.z+p[a].vel.z*dt-0.5*p[a].g*dt*dt;
	      dt=troot-p[w].time;
	      wztemp=p[w].loc.z+TheParams->Ampl*sin(TheParams->Omega*dt);
#if FOLLOW == 1
	      if (a == THIS){
		fprintf(stdout,"ztemp:%f, wztemp:%f\n",ztemp,wztemp);}
#endif
	      if (ztemp < wztemp+p[a].diam/2.){
		/*There are 2 roots.  We have the first one bounded.
		  Find and return it*/
		tc=findroot(a,w,lbound,troot);
#if FOLLOW == 1
		if (a == THIS){
		  fprintf(stdout,"Found a collision: %f\n",tc);
		}
#endif
		return(tc);
		coll=1;
	      }
	    }
	    /*Now, there are no roots left in that section*/
	  }
	}
      }
      if (coll == 0) {
	//	  fprintf(stdout,"Didnt find collision in 1 or 2, check 3\n");
	/*There may still be a collision in the last section of the curve,
	  where the plate acceleration is again less than that of the
	  balls*/
	rbound=p[w].time+TheParams->Period/2.;
	if (lbound < rbound-TheParams->TimeOne)
	  lbound=rbound-TheParams->TimeOne;
	dt=rbound-p[a].time;
	ztemp=p[a].loc.z+p[a].vel.z*dt-0.5*p[a].g*dt*dt;
	if (ztemp < p[w].loc.z+p[a].diam/2.){
	  /*There is a root in this section*/
	  tc=findroot(a,w,lbound,rbound);
	  coll=1;
	  return(tc);
	}
      }
      if (coll == 0) {
	/*There are no ball wall collisions*/
	//	  fprintf(stdout,"Nope, no collisions at all\n");
	return(-20.);
      }
    }
  }
}

#endif

/* Find the collision of ball a and wall w between times lbound and rbound*/

double findroot(int a,int w,double lbound,double rbound) {
 
  double bt,dt,x1,x2,zo,vo,xacc,xh,xl,rts;
  double dxold,dx,zto,f,df,temp,fl,fh;
  double rtsp,dxh,factor=1.;
  int count;
  int MAXIT = 100;
  int j;

/*First, set t=0 to the beginning of a cycle.*/
  if (p[w].g > 0){
    /*Plate on upper cycle*/
    bt=p[w].time;
    dt = p[a].time - bt;
  }
  else {
    /*Plate on lower cycle*/
    bt= p[w].time - TheParams->Period/2.;
    dt= p[a].time -bt;
  }

  x1=lbound-p[a].time;
  x2=rbound-p[a].time;

//  zo=p[a].loc.z + p[a].vel.z * dt - 0.5 * p[a].g * dt * dt;
//  vo=p[a].vel.z - p[a].g * dt;

   zo=p[a].loc.z;
   vo=p[a].vel.z;

#if FOLLOW == 1
  if (a == THIS){
    fprintf(stdout,"zo: %f vo:%f\n",zo,vo);
    fprintf(stdout,"p[a].time %f\n",p[a].time);
  }
#endif

//  xacc=1.0e-8;
  xacc = ROOTACC;

  xh=x1;
  xl=x2;
  
  rts=0.5*(x1+x2);
  dxold=fabs(x2-x1);
  dx=dxold;

  zto=zo-p[w].loc.z-p[a].diam/2.;

#if FOLLOW == 1
  if (a == THIS){
    fprintf(stdout,"zto: %f, p[a].rad:%f\n",zto,p[a].diam/2.);
  }
#endif

  fl=zto + vo*xl - 0.5*p[a].g*xl*xl - TheParams->Ampl*sin(TheParams->Omega*(xl+dt));
  fh=zto + vo*xh - 0.5*p[a].g*xh*xh - TheParams->Ampl*sin(TheParams->Omega*(xh+dt));


#if FOLLOW == 1
  if (a == THIS){
  fprintf(stdout,"xl: %g, fl: %g \n",xl,fl);
  fprintf(stdout,"xh: %g, fh: %g \n",xh,fh);
}
#endif

//if ((-(2e-14)< fh) && (fh < 0.)){
if (fh < 0.) {
   if (fh < worstdz)
     worstdz = fh;
   double fhn;
   double dfh;
   count=1;
   factor=1;
   xh=x1+xacc*factor;
   fhn=zto + vo*xh - 0.5*p[a].g*xh*xh - TheParams->Ampl*sin(TheParams->Omega*(dt+xh)); 
   dfh=vo - p[a].g*xh - TheParams->Ampl*TheParams->Omega*cos(TheParams->Omega*(dt+xh));
   if (dfh>0) {
   fh=fhn;
   while (fh < 0) {
    xh=xh+xacc;
    fhn=zto + vo*xh - 0.5*p[a].g*xh*xh - TheParams->Ampl*sin(TheParams->Omega*(dt+xh));  
    if (count>10){
      factor = factor * 10;
      count=0;
    }
    if (fhn < -1e-2){
      fprintf(stdout,"fhn<fh (case 1)\n");
      fprintf(stdout,"Post Mortem:\n");
      fprintf(stdout,"============\n");
      fprintf(stdout,"xh: %g fh: %g fhn: %g dfh:%g\n",xh,fh,fhn,dfh);
      fprintf(stdout,"xacc: %g\n",xacc);
      fprintf(stdout,"zto:%f vo: %f\n",zto,vo); 
      fprintf(stdout,"Amplitude: %f, Omega: %f, dt: %g\n",TheParams->Ampl,TheParams->Omega,dt);
      fprintf(stdout,"worstdz=%g a=%i\n",worstdz,a);
      fprintf(stdout,"factor: %f count %f\n",factor,count);
      assert(1==0);
    }
    fh=fhn;
    count+=1;
    }}
   else{
    count=0;
    xh=x1-xacc;
    fh=zto + vo*xh - 0.5*p[a].g*xh*xh - TheParams->Ampl*sin(TheParams->Omega*(dt+xh));
    while (fh < 0){
     xh=xh-factor*xacc;
     fhn=zto + vo*xh - 0.5*p[a].g*xh*xh - TheParams->Ampl*sin(TheParams->Omega*(dt+xh));
     if (count > 10){
      factor=factor*10; 
      count=0;
    }
     if (fhn < -1e-2){
/*      fprintf(stdout,"fhn<fh (case 2)\n");
      fprintf(stdout,"Going to try going the other way now.\n");
      fprintf(stdout,"xh: %g fh: %g fhn: %g\n",xh,fh,fhn);
      fprintf(stdout,"xacc: %g\n",xacc);
      fprintf(stdout,"zto:%f vo: %f\n",zto,vo); 
      fprintf(stdout,"Amplitude: %f, Omega: %f, dt: %g\n",TheParams->Ampl,TheParams->Omega,dt);
      fprintf(stdout,"worstdz=%f a=%i\n",worstdz,a); */
      factor=1.;
      count=0;
      xh=x1+xacc*factor;
      fhn=zto + vo*xh - 0.5*p[a].g*xh*xh - TheParams->Ampl*sin(TheParams->Omega*(dt+xh));
      fh=fhn;
      while (fh < 0) {
	xh=xh+xacc;
	fhn=zto + vo*xh - 0.5*p[a].g*xh*xh - TheParams->Ampl*sin(TheParams->Omega*(dt+xh));  
	if (count>10){
	  factor = factor * 10;
	  count=0;
	}
	if (fhn < -1e-2){
	  fprintf(stdout,"fhn<fh (case 3 -- Really sucks.)\n");
	  fprintf(stdout,"Post Mortem:\n");
	  fprintf(stdout,"============\n");
	  fprintf(stdout,"xh: %g fh: %g fhn: %g\n",xh,fh,fhn);
          fprintf(stdout,"dfh: %f\n",dfh);
	  fprintf(stdout,"xacc: %g\n",xacc);
	  fprintf(stdout,"zto:%f vo: %f\n",zto,vo); 
	  fprintf(stdout,"Amplitude: %f, Omega: %f, dt: %g\n",TheParams->Ampl,TheParams->Omega,dt);
	  fprintf(stdout,"worstdz=%g a=%i\n",worstdz,a);
          fprintf(stdout,"factor: %f count %f\n",factor,count);
          fprintf(stdout,"x:%f y:%f\n",p[a].loc.x,p[a].loc.y);
          fprintf(stdout,"It had %d collisons\n",p[a].c);
          fprintf(stdout,"0 had %d collisons\n",p[0].c);
          fprintf(stdout,"100 had %d collisons\n",p[100].c);
          fprintf(stdout,"500 had %d collisons\n",p[500].c);
          fprintf(stdout,"1000 had %d collisons\n",p[1000].c);
	  assert(1==0);
	}
	fh=fhn;
	count+=1;
      }
      
    /*  fprintf(stdout,"Post Mortem:\n");
      fprintf(stdout,"============\n");
      fprintf(stdout,"xh: %g fh: %g fhn: %g\n",xh,fh,fhn);
      fprintf(stdout,"xacc: %g\n",xacc);
      fprintf(stdout,"zto:%f vo: %f\n",zto,vo); 
      fprintf(stdout,"Amplitude: %f, Omega: %f, dt: %g\n",TheParams->Ampl,TheParams->Omega,dt);
      fprintf(stdout,"worstdz=%f a=%i\n",worstdz,a);
      assert (1==0);*/}
     fh=fhn;
     count+=1; }} 
   dxh=xacc*count;
  if (dxh > worstdt) 
    worstdt = dxh;
}
   

 
/* Theres a difference between the time precision and the spatial precision.
   Above line demands that we hold spacial precision to the imposed standard
   of the temporal.  Let this slide, and see if a change in xh (either forward
   _OR_ backwards in time (by the accuracy) is enough to get us back on top */
/*However, even this doesn't work.  I believe that what is going on is that in 
ball ball, the ball is being put exactly on the plate.  Then, we are going 
through some dopey operations changing where t=0 is, and that is introducing
roundoff error on the order of 10^-14.  So.  If you are below, check to make 
sure you are going out.  Die if not.  If you are, move forward in steps of xacc
until you are above the plate.   This explains why increasing the precision
made things worse -- I was only allowing one change by the precision.*/  

/*if (fh < 0.){
#if FOLLOW == 1
  if (a == THIS)
  fprintf(stdout,"Below. fh=%g a=%i time=%f\n",fh,a,Gtime);
#endif
  float fhn;
  xh = x1 + xacc;
  fhn=zto + vo*xh - 0.5*p[a].g*xh*xh - TheParams->Ampl*sin(TheParams->Omega*(dt+xh));
#if FOLLOW == 1                                                                 
  if (a == THIS){  
  fprintf(stdout,"Below. fh=%g\n",fh);
  fprintf(stdout,"Increasing xh by acc.  Now, fhn=%g\n",fhn);}
#endif
  if (fhn < 0.){
    xh = x1 - xacc;
    fhn=zto + vo*xh - 0.5*p[a].g*xh*xh - TheParams->Ampl*sin(TheParams->Omega*(dt+xh));
#if FOLLOW == 1                                                                 
  if (a == THIS)
    fprintf(stdout,"fhn is negative, so reduce xh by acc, now fhn=%g\n",fhn);
#endif
  }
  fh = fhn;
#if FOLLOW == 1                                                                 
  if (a == THIS)
  fprintf(stdout,"Getting out with fh=%g\n",fh);
#endif
}*/


if (fl * fh > 0){
    fprintf(stdout,"Oh shit, the Root isnt bounded in findroot: %i\n",a);
    fprintf(stdout,"Here comes the stuff:\n");
    fprintf(stdout,"a: %i, ay: %f, az: %f\n",a,p[a].loc.y,p[a].loc.z);
    fprintf(stdout,"vay: %f, vaz: %f ,patime: %f\n",p[a].vel.z,p[a].vel.z,p[a].time);
    fprintf(stdout,"p[a].diam:%f\n",p[a].diam);
    fprintf(stdout,"p[w].time:%f, p[w].z: %f\n",p[w].time,p[w].loc.z);
    fprintf(stdout,"fl: %g, fh: %g\n",fl,fh);
    fprintf(stdout,"xl: %g, xh: %g\n",xl,xh);
    bomb(0,a);}

  rtsp=dt+rts;
  f = zto + vo*rts - 0.5*p[a].g*rts*rts - TheParams->Ampl*sin(TheParams->Omega*rtsp);
  df = vo - p[a].g * rts - TheParams->WallVel * cos(TheParams->Omega * rtsp);

//  fprintf(stdout,"Particle:%i \n",a);

  for (j=1;j<=MAXIT;j++) {
#if FOLLOW == 1
  if (a == THIS){
   fprintf(stdout,"xl: %f, xh:%f, dx: %f\n",xl,xh,dx);
  }
#endif 
   /* IF NR goes out of bounds, or if not decreasing fast, do bisection*/

    if ((((rts-xh)*df-f)*((rts-xl)*df-f) >= 0.0) || (fabs(2.0*f) > fabs(dxold*df))) {  
      dxold=dx;
      dx=0.5*(xh-xl);
      rts=xl+dx;
      if (xl == rts) return rts+p[a].time;
    }
    else {
      dx=f/df;
      temp=rts;
      rts -= dx;
      if (temp == rts) return rts+p[a].time;
    }
    if (fabs(dx) < xacc) return rts+p[a].time;
    rtsp=rts+dt;
    f = zto + vo*rts - 0.5*p[a].g*rts*rts - TheParams->Ampl*sin(TheParams->Omega*rtsp);
    df = vo - p[a].g * rts - TheParams->WallVel * cos(TheParams->Omega * rtsp);
    if (f < 0.0)
      xl=rts;
    else
      xh=rts;
  }
  fprintf(stdout,"Convergence on root of pos is sucky -- 1.\n");
  bomb(0,a);
  return HUGE;
}

double findvroot(int a,int w,double lbound,double rbound) {
 
  double bt,dt,x1,x2,vo,xacc;
  double fl,fh,xl,xh,swap;
  double rts,dx,dxold,temp,f,df;
  int MAXIT = 100;
  int j;

/*First, set t=0 to the beginning of a cycle.*/
  if (p[w].g > 0){
    /*Plate on upper cycle -- This should only be the case*/
    bt=p[w].time;
    dt = bt - p[a].time;
  }
  else {
    /*Plate on lower cycle*/
    fprintf(stderr,"Major logic problem: see findvroot. /n");
    bomb(4,a);
  }
  x1=lbound-bt;
  x2=rbound-bt;

  vo=p[a].vel.z - p[a].g * dt;

  xacc=1.0e-7;
  MAXIT = 100;

  fl = vo - p[a].g * x1 - TheParams->WallVel * cos(TheParams->Omega * x1);
  fh = vo - p[a].g * x2 - TheParams->WallVel * cos(TheParams->Omega * x2);
  
  if (fl * fh > 0){
    fprintf(stdout,"Oh shit, the Root isnt bounded in findvroot: %i\n",a);
    fprintf(stdout,"fl: %f fh: %f\n",fl,fh);
    return(-456.);
    bomb(1,a);}

  if (fl < 0.) {
    xl=x1;
    xh=x2;}
  else {
    xh=x1;
    xl=x2;
    swap=fl;
    fl=fh;
    fh=swap;
  }

#if FOLLOW == 1
  if (a == THIS){
    fprintf(stdout,"xl: %f fl:%f\n",xl,fl);
    fprintf(stdout,"xh: %f fh:%f\n",xh,fh);
  }
#endif

  rts=0.5*(x1+x2);
  dxold=fabs(x2-x1);
  dx=dxold;

  f = vo - p[a].g * rts - TheParams->WallVel * cos(TheParams->Omega * rts);
  df = -p[a].g + p[w].g * sin(TheParams->Omega*rts);

  for (j=1;j<=MAXIT;j++) {
 
   /* IF NR goes out of bounds, or if not decreasing fast, do bisection*/

    if ((((rts-xh)*df-f)*((rts-xl)*df-f) >= 0.0) || (fabs(2.0*f) > fabs(dxold*df))) {  
      dxold=dx;
      dx=0.5*(xh-xl);
      rts=xl+dx;
      if (xl == rts) return rts+bt;
    }
    else {
      dx=f/df;
      temp=rts;
      rts -= dx;
      if (temp == rts) return rts+bt;
    }
    if (fabs(dx) < xacc) return rts+bt;
    f = vo - p[a].g * rts - TheParams->WallVel * cos(TheParams->Omega * rts);
    df = -p[a].g + p[w].g * sin(TheParams->Omega*rts);          
    if (f < 0.0)
      xl=rts;
    else
      xh=rts;
  }
  fprintf(stdout,"Convergence on root is sucky -- 2.\n");
  bomb(0,a);
  return HUGE;
}  

     

/* Determines whether two particles *may possibly* collide by checking for collisions in one dimension.  The value of iPlane determines which dimension is to be checked.  iPlane = (0,1,2) for (x,y,z) respectively.  This function returns 1 if the 1D collision occured for the plane specified.  If the 1d collision is not detected, then 0 is returned */

int c1detect(int a, int b, int iPlane) {
  double aVel = (double) *(((double *) &p[a].vel) + iPlane);
  double bVel = (double) *(((double *) &p[b].vel) + iPlane);
  double aLoc = (double) *(((double *) &p[a].loc) + iPlane);
  double bLoc = (double) *(((double *) &p[b].loc) + iPlane);
  char cPlane[3] = { 'x', 'y', 'z' };
  int retValue = 1;
  if (( (bLoc - aLoc)*(bVel-aVel) <= 0.0) || ((bLoc - aLoc)*(bLoc-aLoc) <= TheParams->pdiam * TheParams->pdiam))
    retValue = 1;
  else
    retValue = 0;
  return(retValue);
}


int cxdetect(int a, int b) {
  int retValue = 1;
  double junk = TheParams->pdiam;
  if (p[b].loc.x - p[a].loc.x > 0)
	junk = -junk;
  if ((p[b].loc.x - p[a].loc.x + junk)*(p[b].vel.x - p[a].vel.x) <= 0.0)
    retValue = 1;
  else
    retValue = 0;
  return(retValue);
}

int cydetect(int a, int b) {
  int retValue = 1;
  double junk = TheParams->pdiam;
  if (p[b].loc.y - p[a].loc.y > 0)
	junk = -junk;
  if ((p[b].loc.y- p[a].loc.y + junk)*(p[b].vel.y - p[a].vel.y) <= 0.0)
    retValue = 1;
  else
    retValue = 0;
  return(retValue);
}

int czdetect(int a, int b) {
  int retValue = 1;
  double junk = TheParams->pdiam;
  if (p[b].loc.z - p[a].loc.z > 0)
	junk = -junk;
  if ((p[b].loc.z - p[a].loc.z + junk)*(p[b].vel.z - p[a].vel.z) <= 0.0)
    retValue = 1;
  else
    retValue = 0;
  return(retValue);
}


/* c3detect calculates the collision of two particles a and b in 3D.  The
value returned is the collision time.  If the collision time is negative,
then it is invalid and the particles do not collide.  Any positive value
represents a valid collision.  
*/

double c3detect(int a, int b) {
   double DeltaVx, DeltaVy, DeltaVz, DeltaPx, DeltaPy, DeltaPz;
   double Aterm, Bterm, Cterm, Bsqr_4ac, Ctime1, Ctime2;
   double templax,templay,templaz,templbx,templby,templbz;
   double tempvax,tempvay,tempvaz,tempvbx,tempvby,tempvbz;
   double deltaT;
   double sb,q,r1,r2;
   double diam=(p[a].diam + p[b].diam)/2.;
   double ddt,ddp;
   int fail;
   
#ifdef GRAVDIM 
   if (p[a].gvec.x != p[b].gvec.x || p[a].gvec.y !=p[b].gvec.y || p[a].gvec.z != p[b].gvec.z)
    return(c4detect(a,b));
#endif

   deltaT = p[a].time - p[b].time;

#if DIMENSION == 3
   templbx = p[b].loc.x + p[b].vel.x * deltaT;
#endif

   templby = p[b].loc.y + p[b].vel.y * deltaT;
   templbz = p[b].loc.z + p[b].vel.z * deltaT - 0.5 * p[b].g * deltaT * deltaT;
   tempvbz = p[b].vel.z - p[b].g * deltaT;
   
#if DIMENSION == 3
   DeltaVx = p[a].vel.x - p[b].vel.x;
#endif

   DeltaVy = p[a].vel.y - p[b].vel.y;
   DeltaVz = p[a].vel.z - tempvbz;

#if DIMENSION ==3
   DeltaPx = p[a].loc.x - templbx;
#endif

   DeltaPy = p[a].loc.y - templby;
   DeltaPz = p[a].loc.z - templbz; 


#if PERIODIC 
#if DIMENSION == 3
    ddt=Gtime-p[a].time;
    ddp=DeltaPx+DeltaVx*ddt;
    fail =0;
    while (fabs(ddp) > 2. && fail < 100){
       if (ddp > 0){
         DeltaPx-=XBSIZE; 
         ddp=DeltaPx+DeltaVx*ddt;
        }
       else{
         DeltaPx+=XBSIZE;
         ddp=DeltaPx+DeltaVx*ddt;
       }
       fail++;
    }
     if (fabs(ddp) > 2.){
      fprintf(stdout,"x, ddp: %f fail:%i\n",ddp,fail);
      fprintf(stdout,"a: %i b:%i\n",a,b);
      abort();
    }
#endif
#if PERIODIC != 2
    ddt=Gtime-p[a].time;
    ddp=DeltaPy+DeltaVy*ddt;
    fail=0;
    while (fabs(ddp) > 2. && fail<100){
       if (ddp > 0){
         DeltaPy-=YBSIZE; 
         ddp=DeltaPy+DeltaVy*ddt;
        }
       else{
         DeltaPy+=YBSIZE;
         ddp=DeltaPy+DeltaVy*ddt;
       }
       fail ++;
     } 
     if (fabs(ddp) > 2.){
      fprintf(stdout,"a: %i b: %i\n",a,b);
      fprintf(stdout,"a.t: %f b.t: %f\n",p[a].time,p[b].time);
      fprintf(stdout,"a.z: %f b.z: %f\n",p[a].loc.z,p[b].loc.z);
      fprintf(stdout,"a.v.z: %f b.v.z: %f\n",p[a].vel.z,p[b].vel.z);
      fprintf(stdout,"a.c.z: %i b.c.z: %i\n",p[a].cell.z,p[b].cell.z);
      fprintf(stdout,"a.y: %f b.y: %f\n",p[a].loc.y,p[b].loc.y);
      fprintf(stdout,"a.v.y: %f b.v.y: %f\n",p[a].vel.y,p[b].vel.y);
      fprintf(stdout,"a.c.y: %i b.c.y: %i\n",p[a].cell.y,p[b].cell.y);
      fprintf(stdout,"ddt: %f Gtime:%f\n",ddt,Gtime);
      fprintf(stdout,"DeltaPy %f DeltaVy %f\n",DeltaPy,DeltaVy);
      fprintf(stdout,"y, ddp: %f fail:%i\n",ddp,fail);
      abort();
    }
#endif
#if PERIODIC == 3
    ddt=Gtime-p[a].time;
    ddp=DeltaPz+DeltaVz*ddt;
    fail =0;
    while (fabs(ddp) > 2. && fail < 100){
       if (ddp > 0){
         DeltaPz-=ZBSIZE; 
         ddp=DeltaPz+DeltaVz*ddt;
        }
       else{
         DeltaPz+=ZBSIZE;
         ddp=DeltaPz+DeltaVz*ddt;
       }
       fail++;
    }
     if (fabs(ddp) > 2.){
      fprintf(stdout,"x, ddp: %f fail:%i\n",ddp,fail);
      fprintf(stdout,"a: %i b:%i\n",a,b);
      abort();
    }
#endif
#endif


#if DIMENSION == 3
   Aterm = DeltaVx * DeltaVx + DeltaVy * DeltaVy + DeltaVz * DeltaVz;
   Bterm = 2. * (DeltaVx*DeltaPx + DeltaVy*DeltaPy + DeltaVz*DeltaPz);
   Cterm = DeltaPx * DeltaPx + DeltaPy * DeltaPy + DeltaPz * DeltaPz - diam * diam;
#else 
   Aterm = DeltaVy * DeltaVy + DeltaVz * DeltaVz;
   Bterm = 2. * ( DeltaVy*DeltaPy + DeltaVz*DeltaPz);
   Cterm = DeltaPy * DeltaPy + DeltaPz * DeltaPz - diam * diam;
#endif
   
   Bsqr_4ac = Bterm * Bterm - 4. * Aterm * Cterm;
   
if ((Bsqr_4ac < 0) || (Aterm == 0)){
      return(-3.0);     /* roots are imaginary or a solution does not exist */
  }
   

/*   Ctime1 = quadsolve(Aterm,Bterm,Cterm,&Ctime2,1);*/

   if (Bterm < 0)
     sb = -1.;
   else
     sb = 1.;


   q = -.5 * (Bterm + sb * sqrt(Bsqr_4ac));
   r1 = q/Aterm;
   r2 = Cterm/q;


   if (r1<r2){
     return(r1+p[a].time);
   }
   else{
     return(r2+p[a].time);
   }

/*   Ctime1 += p[a].time;
   Ctime2 += p[a].time;
   if (Ctime1 < Ctime2)
     return(Ctime1);
   else
     return(Ctime2);*/
}

// An extended precision version of c3detect.  In addition to a and b, 
// factor is sent.  This factor is a scale for the positions and times, 
// leaving the velocities unaltered.  The time is returned before being added 
// to the Global time, for correct use in ballball.

double cpdetect(int a, int b, double factor) {
   double DeltaVx, DeltaVy, DeltaVz, DeltaPx, DeltaPy, DeltaPz;
   double Aterm, Bterm, Cterm, Bsqr_4ac, Ctime1, Ctime2;
   double templax,templay,templaz,templbx,templby,templbz;
   double tempvax,tempvay,tempvaz,tempvbx,tempvby,tempvbz;
   double deltaT;
   double diam = (p[a].diam + p[b].diam)/2.;
   
   deltaT = factor * (p[a].time - p[b].time);
   templbx = p[b].loc.x + p[b].vel.x * deltaT;
   templby = p[b].loc.y + p[b].vel.y * deltaT;
   templbz = p[b].loc.z + p[b].vel.z * deltaT - 0.5 * p[b].g * deltaT * deltaT;
   tempvbz = p[b].vel.z - p[b].g * deltaT;
   
   DeltaVx = factor * (p[a].vel.x - p[b].vel.x);
   DeltaVy = factor * (p[a].vel.y - p[b].vel.y);
   DeltaVz = factor * (p[a].vel.z - tempvbz);
   DeltaPx = p[a].loc.x - templbx;
   DeltaPy = p[a].loc.y - templby;
   DeltaPz = p[a].loc.z - templbz; 
   Aterm = DeltaVx * DeltaVx + DeltaVy * DeltaVy + DeltaVz * DeltaVz;
   Bterm = 2 * (DeltaVx*DeltaPx + DeltaVy*DeltaPy + DeltaVz*DeltaPz);
   Cterm = DeltaPx * DeltaPx + DeltaPy * DeltaPy + DeltaPz * DeltaPz - factor*factor*(diam * diam);
   Bsqr_4ac = Bterm * Bterm - 4 * Aterm * Cterm;
//   if (a==15 && b==13){
//     printf("wtf a=15 b=13, A=%f, B=%f, C=%f, D=%f\n",Aterm,Bterm,Cterm,Bsqr_4//ac);
//     printf("wtf a=15: y=%f, z=%f, t=%f\n",p[a].loc.y,p[a].loc.z,p[a].time);
//     printf("wtf b=13: y=%f, z=%f, t=%f\n",p[b].loc.y,p[b].loc.z,p[b].time);}
   if ((Bsqr_4ac < 0) || (Aterm == 0))
      return(-3.0);     /* roots are imaginary or a solution does not exist */
//   Ctime1 = (-Bterm + sqrt(Bsqr_4ac))/(2*Aterm) + p[a].time;
//   Ctime2 = (-Bterm - sqrt(Bsqr_4ac))/(2*Aterm) + p[a].time;
   Ctime1 = quadsolve(Aterm,Bterm,Cterm,&Ctime2,1);
   if (Ctime1 < Ctime2)
     return(Ctime1/factor);
   else
     return(Ctime2/factor);
}


double vdetect(int a, int b) {
  double t_c;
  double deltaT = Gtime - p[a].time;
  double plx,ply;
  int c;
  if (p[a].pty == SPHERE) {


#if DIMENSION == 3
    if (b == TheParams->plusx) {
#ifdef GRAVDIM
        return(xydetect(a,b));
#endif
        c=p[a].cell.x;
#if PERIODIC
        while (c < p[a].loc.x+p[a].vel.x*deltaT)
          c+=XBSIZE;
#endif
	t_c = (c - p[a].loc.x - p[a].vel.x * deltaT) / p[a].vel.x;
	return(t_c + Gtime);
    }
    if (b == TheParams->negx) {
#ifdef GRAVDIM
        return(xydetect(a,b));
#endif
      if (p[a].vel.x < 0) {
        c=p[a].cell.x;
        plx=p[a].loc.x;
#if PERIODIC
        while (p[a].loc.x+p[a].vel.x*deltaT < c-1)
           c-=XBSIZE;
#endif
	t_c = (c - 1 - p[a].loc.x - p[a].vel.x * deltaT) / p[a].vel.x;
	return(t_c + Gtime);
      }
    }
#endif
  

   if (b == TheParams->plusy) {
#ifdef GRAVDIM
        return(xydetect(a,b));
#endif
        c=p[a].cell.y;
        //ply=p[a].loc.y;
#if PERIODIC != 2
        while (c < p[a].loc.y+p[a].vel.y*deltaT)
          c+=YBSIZE;
#endif
	t_c = (c - p[a].loc.y - p[a].vel.y * deltaT) / p[a].vel.y;
	return(t_c + Gtime);
    }

    if (b == TheParams->negy) {
#ifdef GRAVDIM
        return(xydetect(a,b));
#endif
      if (p[a].vel.y < 0) {
        c=p[a].cell.y;
        //ply=p[a].loc.y;
#if PERIODIC != 2
        while (c-1 > p[a].loc.y+p[a].vel.y*deltaT)
          c-=YBSIZE;
#endif
	t_c = (c - 1 - p[a].loc.y - p[a].vel.y * deltaT) / p[a].vel.y;
	return(t_c + Gtime);
      }
    }

    if (b == TheParams->plusz) {
#if GRAV == 1
	  return(zdetect(a,b));
#else
	if (p[a].vel.z > 0) {
          c=p[a].cell.z;
#if PERIODIC == 3
          while (c < p[a].loc.z+p[a].vel.z*deltaT)
            c+=ZBSIZE;
#endif
	  t_c = (c - p[a].loc.z - p[a].vel.z * deltaT) / p[a].vel.z;
	  return(t_c + Gtime);
	}
#endif
    }

    if (b == TheParams->negz) {
#if GRAV == 1
	return(zdetect(a,b));
#else
	if (p[a].vel.z < 0) {
          c=p[a].cell.z;
#if PERIODIC == 3
          while (c-1 > p[a].loc.z+p[a].vel.z*deltaT)
            c-=ZBSIZE;
#endif
	  t_c = (c - 1 - p[a].loc.z - p[a].vel.z * deltaT) / p[a].vel.z;
	  return(t_c + Gtime);
	}
#endif
    }

#if THERMAL == 1
    if (b == TheParams->ntherm || b == TheParams->ptherm)
        return(zdetect(a,b));
#endif

  return(-1);
  }
  return(-1);
}

/*First, we check to see if the equation is even allowed.  To do that, solve 
for collistion time ranges in 3-D (This is solving 4 linear equations and 2
quadratics.)  Then see if the ranges all overlap.  If they do, we have to solve
a quartic.  This involves first solving a cubic, then two quadratics.*/

double c4detect(int a, int b)
{
#ifdef GRAVDIM
  int fail;
  double ddt,ddp;
  double templbx,templby,templbz,tempvbz,tempvbx,tempvby;
  double Deltax,Deltay,Deltaz,DeltaVx,DeltaVy,DeltaVz;
  double DeltaGx,DeltaGy,DeltaGz;
  double a0,a1,a2,a3,a4;
  double tx1,tx2,ty1,ty2,tz1,tz2,tz3,tz4,temp;
  double deltaT,tc;
  double diam = (p[a].diam + p[b].diam)/2.;
 
  deltaT = p[a].time - p[b].time;
  templbx = p[b].loc.x + p[b].vel.x * deltaT-0.5*p[b].gvec.x * deltaT * deltaT;
  templby = p[b].loc.y + p[b].vel.y * deltaT-0.5*p[b].gvec.y * deltaT * deltaT;
  templbz = p[b].loc.z + p[b].vel.z * deltaT-0.5*p[b].gvec.z * deltaT * deltaT;
  tempvbx = p[b].vel.x - p[b].gvec.x * deltaT;
  tempvby = p[b].vel.y - p[b].gvec.y * deltaT;
  tempvbz = p[b].vel.z - p[b].gvec.z * deltaT;
  
  DeltaVx = p[a].vel.x - tempvbx;
  DeltaVy = p[a].vel.y - tempvby;
  DeltaVz = p[a].vel.z - tempvbz;
  Deltax = p[a].loc.x - templbx;
  Deltay = p[a].loc.y - templby;
  Deltaz = p[a].loc.z - templbz;
  DeltaGx = p[a].gvec.x - p[b].gvec.x;
  DeltaGy = p[a].gvec.y - p[b].gvec.y;
  DeltaGz = p[a].gvec.z - p[b].gvec.z;
 
#if PERIODIC 
#if DIMENSION == 3
    ddt=Gtime-p[a].time;
    ddp=Deltax+DeltaVx*ddt-.5*DeltaGx*ddt*ddt;
    fail =0;
    while (fabs(ddp) > 2. && fail < 100){
       if (ddp > 0){
         Deltax-=XBSIZE; 
         ddp=Deltax+DeltaVx*ddt-.5*DeltaGx*ddt*ddt;
        }
       else{
         Deltax+=XBSIZE;
         ddp=Deltax+DeltaVx*ddt-.5*DeltaGx*ddt*ddt;
       }
       fail++;
    }
     if (fabs(ddp) > 2.){
      fprintf(stdout,"x, ddp: %f fail:%i\n",ddp,fail);
      fprintf(stdout,"a: %i b:%i\n",a,b);
      abort();
    }
#endif
#if PERIODIC != 2
    ddt=Gtime-p[a].time;
    ddp=Deltay+DeltaVy*ddt-.5*DeltaGy*ddt*ddt;
    fail=0;
    while (fabs(ddp) > 2. && fail<100){
       if (ddp > 0){
         Deltay-=YBSIZE; 
         ddp=Deltay+DeltaVy*ddt-.5*DeltaGy*ddt*ddt;
        }
       else{
         Deltay+=YBSIZE;
         ddp=Deltay+DeltaVy*ddt-.5*DeltaGy*ddt*ddt;
       }
       fail ++;
     } 
     if (fabs(ddp) > 2.){
      fprintf(stdout,"a: %i b: %i\n",a,b);
      fprintf(stdout,"a.t: %f b.t: %f\n",p[a].time,p[b].time);
      fprintf(stdout,"a.z: %f b.z: %f\n",p[a].loc.z,p[b].loc.z);
      fprintf(stdout,"a.v.z: %f b.v.z: %f\n",p[a].vel.z,p[b].vel.z);
      fprintf(stdout,"a.c.z: %i b.c.z: %i\n",p[a].cell.z,p[b].cell.z);
      fprintf(stdout,"a.y: %f b.y: %f\n",p[a].loc.y,p[b].loc.y);
      fprintf(stdout,"a.v.y: %f b.v.y: %f\n",p[a].vel.y,p[b].vel.y);
      fprintf(stdout,"a.c.y: %i b.c.y: %i\n",p[a].cell.y,p[b].cell.y);
      fprintf(stdout,"ddt: %f Gtime:%f\n",ddt,Gtime);
      fprintf(stdout,"DeltaPy %f DeltaVy %f\n",Deltay,DeltaVy);
      fprintf(stdout,"y, ddp: %f fail:%i\n",ddp,fail);
      abort();
    }
#endif
#if PERIODIC == 3
    ddt=Gtime-p[a].time;
    ddp=Deltaz+DeltaVz*ddt-.5*DeltaGz*ddt*ddt;
    fail =0;
    while (fabs(ddp) > 2. && fail < 100){
       if (ddp > 0){
         Deltaz-=ZBSIZE; 
         ddp=Deltaz+DeltaVz*ddt-.5*DeltaGz*ddt*ddt;
        }
       else{
         Deltaz+=ZBSIZE;
         ddp=Deltaz+DeltaVz*ddt-.5*DeltaGz*ddt*ddt;
       }
       fail++;
    }
     if (fabs(ddp) > 2.){
      fprintf(stdout,"x, ddp: %f fail:%i\n",ddp,fail);
      fprintf(stdout,"a: %i b:%i\n",a,b);
      abort();
    }
#endif
#endif

/*
  if (DeltaVx !=0.){
    tx1 = (diam-Deltax)/DeltaVx;
    tx2 = -(diam+Deltax)/DeltaVx;
    if (tx2 < tx1){
      temp=tx1;
      tx1=tx2;
      tx2=temp;
    }
  }
  else {
    if ((Deltax < diam) && (Deltax > -diam)){
      tx1=Gtime-999.;
      tx2=Gtime+999.;
    }
    else{
      tx1=-999.;
      tx2=-999.;
    }
  }
  
  if (DeltaVy !=0.){
    ty1 = (diam-Deltay)/DeltaVy;
    ty2 = -(diam+Deltay)/DeltaVy;
    if (ty2 < ty1){
      temp=ty1;
      ty1=ty2;
      ty2=temp;
    }
  }
  else {
    if ((Deltay < diam) && (Deltay > -diam)){
      ty1=Gtime-999.;
      ty2=Gtime+999.;
    }
    else{
      ty1=-999.;
      ty2=-999.;
    }
  }  
  
 
  tx1=quadsolve(-DeltaGx/2.,DeltaVx,Deltax-diam,&tx4,1);
  tx2=quadsolve(-DeltaGx/2.,DeltaVx,Deltax+diam,&tx3,1);
  if (tx1 > tx4)
    {
      temp = tx1;
      tx1=tx4;
      tx4=temp;
    }
  if (tx2 > tx3)
    {
      temp = tx3;
      tx3 = tx2;
      tx2 = temp;
    }
  if (tx2 == -831.)
    {
      tx2 = tx1;
      tx3 = tx4;
    }
  if (tx1 == -831.)
    {
      tx1 = tx2;
      tx4 = tx3;
    }
  if (tx2 < tx1)
    {
      temp = tx1;
      tx1 = tx2;
      tx2 = temp;
      temp = tx3;
      tx3=tx4;
      tx4 = temp;
    }

  if (!((tx1 <= tx2) && (tx2 <= tx3) && (tx3 <= tx4))) {
     fprintf(stdout,"Death in c4detect\n");
     assert ((tx1 <= tx2) && (tx2 <= tx3) && (tx3 <= tx4));}
   
  
  if ( (tx2 < 0.) || (ty2 < 0.) || ((tz2 < 0.) && (tz4 < 0.))){
 
  tz1=quadsolve(-DeltaG/2.,DeltaVz,Deltaz-diam,&tz4,1);
  tz2=quadsolve(-DeltaG/2.,DeltaVz,Deltaz+diam,&tz3,1);
  if (tz1 > tz4)
    {
      temp = tz1;
      tz1=tz4;
      tz4=temp;
    }
  if (tz2 > tz3)
    {
      temp = tz3;
      tz3 = tz2;
      tz2 = temp;
    }
  if (tz2 == -831.)
    {
      tz2 = tz1;
      tz3 = tz4;
    }
  if (tz1 == -831.)
    {
      tz1 = tz2;
      tz4 = tz3;
    }
  if (tz2 < tz1)
    {
      temp = tz1;
      tz1 = tz2;
      tz2 = temp;
      temp = tz3;
      tz3=tz4;
      tz4 = temp;
    }

  if (!((tz1 <= tz2) && (tz2 <= tz3) && (tz3 <= tz4))) {
     fprintf(stdout,"Death in c4detect\n");
     assert ((tz1 <= tz2) && (tz2 <= tz3) && (tz3 <= tz4));}
   
  
  if ( (tx2 < 0.) || (ty2 < 0.) || ((tz2 < 0.) && (tz4 < 0.))){
    return (-999.);
  }
  if ((tx2 < ty1) || (ty2 < tx1) || (tx2 < tz1) || (tx1 > tz4) || ((tx1 > tz2) && (tx2 < tz3)) || (ty2 < tz1) || (ty1 > tz4) || ((ty1 > tz2) && (ty2 < tz3)))
    {
      return (-777.);
    }
*/
      
    /* If we are still here, then there is a pretty good chance of an actual
       collision, and we have to figure out where it will be) */
   

    a4=DeltaGz*DeltaGz/4. + DeltaGy*DeltaGy/4. + DeltaGx*DeltaGx/4.;
    a3=-DeltaGz*DeltaVz-DeltaGy*DeltaVy-DeltaGx*DeltaVx;
    a2=DeltaVx * DeltaVx + DeltaVy*DeltaVy + DeltaVz* DeltaVz - DeltaGz*Deltaz
       -DeltaGx * Deltax - DeltaGy*Deltay;
    a1=2.*(Deltax*DeltaVx + Deltay*DeltaVy + Deltaz*DeltaVz);
    a0=Deltax*Deltax + Deltay*Deltay + Deltaz*Deltaz;
   
/*    if ((a==425 || b==425) && (a==1642 || b==1642)) 
    tc=quartsolve((a0-diam*diam)/a4,a1/a4,a2/a4,a3/a4,a4,1);
    else
*/
    tc=quartsolve((a0-diam*diam)/a4,a1/a4,a2/a4,a3/a4,a4,0);
 
/*    if ((a==425 || b==425) && (a==1642 || b==1642)) {
    if (tc>0)
    fprintf(stdout,"c4detect picks up collision at %f\n",tc+p[a].time);
    else
    fprintf(stdout,"Not gonna collide\n");
     fprintf(stdout,"Particle %d\n",a);
     fprintf(stdout,"+=============+\n");
     fprintf(stdout,"Position: %f %f \n",p[a].loc.y,p[a].loc.z);
     fprintf(stdout,"Velocity: %f %f \n",p[a].vel.y,p[a].vel.z);
     fprintf(stdout,"Accelera: %f %f \n",p[a].gvec.y,p[a].gvec.z);
     fprintf(stdout,"Time:     %f\n\n",p[a].time);
     fprintf(stdout,"Particle %d\n",b);
     fprintf(stdout,"+=============+\n");
     fprintf(stdout,"Position: %f %f \n",p[b].loc.y,p[b].loc.z);
     fprintf(stdout,"Velocity: %f %f \n",p[b].vel.y,p[b].vel.z);
     fprintf(stdout,"Accelera: %f %f \n",p[b].gvec.y,p[b].gvec.z);
     fprintf(stdout,"Time:     %f\n\n",p[b].time);
     double xa=p[a].loc.x+p[a].vel.x*tc-.5*p[a].gvec.x*tc*tc;
     double ya=p[a].loc.y+p[a].vel.y*tc-.5*p[a].gvec.y*tc*tc;
     double za=p[a].loc.z+p[a].vel.z*tc-.5*p[a].g*tc*tc;
     double newtc=Gtime+tc-p[b].time;
     double xb=p[b].loc.x+p[b].vel.x*newtc-.5*p[b].gvec.x*newtc*newtc;
     double yb=p[b].loc.y+p[b].vel.y*newtc-.5*p[b].gvec.y*newtc*newtc;
     double zb=p[b].loc.z+p[b].vel.z*newtc-.5*p[b].g*newtc*newtc;
     double dx=xa-xb;
     double dy=ya-yb;
     double dz=za-zb;
     fprintf(stdout,"At that time, the distance will be:%f diam:%f \n",sqrt(dx*dx+dy*dy+dz*dz),.5*(p[a].diam+p[b].diam)); 
   } 
*/

   
   
 
    if (tc > 0.) return(tc+p[a].time);
    else return(-666.);
#endif  
}

double quadsolve(double a,double b,double c,double *return2,int flag)
{
  double q,sb,disc,r1,r2;
  disc = b*b - 4. * a * c;
  if (disc < 0)
    {
      *return2 = -830.;
      return(-831.);
    }
  if (b < 0)
    sb = -1.;
  else
    sb = 1.;
  q = -.5 * (b + sb * sqrt(disc));
  r1 = q/a;
  r2 = c/q;

  if (flag == 0)
    {
      if (((r1 > 0.) && (r1 < r2)) || ((r1 > 0.) && (r2 < 0)))
	{
	  *return2 = r2;
	  return(r1);
	}
      if (((r2 > 0.) && (r2 < r1)) || ((r2 > 0.) && (r1 < 0.)))
	{
	  *return2 = r1;
	  return(r2);
	}
      *return2 = -830.;
      return (-832.);
    }
  else
    {
      if (r1 < r2)
	{
	  *return2 = r2;
	  return(r1);
	}
      else 
	{
	  *return2 = r1;
	  return(r2);
	}
    }

}

/* Solve the eqn x^3 + a1 x^2 + a2 x + a3 = 0 */
double cubesolve(double a1, double a2, double a3, double *root2, double *root3)
{
  double Q,R,sqrtQ,pi;
  double r2q3,sR,aR,theta;
  double term1,term2,root1; 

//  printf("Cubic: a1=%f a2=%f a3=%f\n",a1,a2,a3);
 
  Q = (a1 * a1 - 3. * a2)/9.;
  R = (2. * a1 * a1 * a1 - 9. * a1 * a2 + 27. * a3)/54.;
 
  r2q3 = R*R - Q*Q*Q;

//  printf("Cubic: Q=%f R=%f r2q3=%f\n",Q,R,r2q3);

  if (r2q3 > 0.) {
    /*Only one real root*/
    if (R < 0.)
      sR = 1.;
    else
      sR = -1.;
    aR = fabs(R);
    term1 = pow(sqrt(r2q3)+aR,(1./3.));
    term2 = Q/term1;
    root1 = sR*(term1+term2) - a1/3.;
    *root2 = -444.;
    *root3 = -444.;
    return(root1);
  }
  else {
//    printf("Cubic has 3 real roots.\n");
    sqrtQ=sqrt(Q);
    theta=acos(R/(sqrtQ*sqrtQ*sqrtQ));
    pi=acos(-1.);
    root1=-2.*sqrtQ*cos(theta/3.)-a1/3.;
    *root2=-2.*sqrtQ*cos((theta+2.*pi)/3.)-a1/3.;
    *root3=-2.*sqrtQ*cos((theta+4.*pi)/3.)-a1/3.; 
//    printf("wtf: theta=%f sqrtQ=%f a1/3.=%f cos(theta/3.)=%f\n",theta,sqrtQ,a//1/3.,cos(theta/3.));
//    printf("Some roots: pi=%f, root1=%f, root2=%f, root3=%f\n",pi,root1,*root//2,*root3);
    return(root1);
  }
}

/*Solve the Quartic z^4 + a3 z^3 + a2 z^2 + a1 z +a0. See page 34 of Beyer*/
double quartsolve(double a0,double a1,double a2,double a3,double a4,int debug)
{
  double u1,b,c,cc2,cc1,cc0,dum;
  double r1,r2,u2,u3,r3,r4;
  int count=0;
//  if (debug)
//    printf("a4=%f a3=%f a2=%f a1=%f a0=%f\n",a4,a3,a2,a1,a0);
  /*First we solve a cubic equation*/
  cc2=-a2;
  cc1=(a1*a3-4.*a0);
  cc0=-(a1*a1+a0*a3*a3-4.*a0*a2);
  u1=cubesolve(cc2,cc1,cc0,&u2,&u3);
  //fprintf(stdout,"Did a cubic: x^3 + %f x^2 + %f x +%f\n",cc2,cc1,cc0);
/* if (debug){
  printf("The roots: u1=%f u2=%f u3=%f\n",u1,u2,u3);
  double test=u1*u1*u1+cc2*u1*u1+cc1*u1+cc0;
  printf("test u1:%f\n",test);
  test=u2*u2*u2+cc2*u2*u2+cc1*u2+cc0;
  printf("test u2:%f\n",test);
  test=u3*u3*u3+cc2*u3*u3+cc1*u3+cc0;
  printf("test u3:%f\n",test);
 }
*/


  if ((u2 != -444.) || (u3 != -444.)){
/*    if ((u1 + .25*a3*a3 - a2 > 0.) && (.25*u1*u1 - a0 >0.)) {
      u1=u1;
      count=count+1;
    }
    if ((u2 + .25*a3*a3 - a2 > 0.) && (.25*u2*u2 - a0 >0.)){
      u1=u2;
      count=count+1;
    }
    if ((u3 + .25*a3*a3 - a2 > 0.) && (.25*u3*u3 - a0 >0.)){
  u1=u3;
      count=count+1;
    }
*/
   if (u2 > u1)
     u1 = u2;
   if (u3 > u1)
     u1 = u3;
  }

 //fprintf(stdout,"%f\n",u1);

  /*Now we have 2 quadratic equations
  b=a3/2.-sqrt(a3*a3/4.+u1-a2);
  c=u1/2.+sqrt(u1*u1/4.-a0);
  r1=quadsolve(1.,b,c,&dum,0);
  //fprintf(stdout,"Solved this quadratic: %f %f\n",b,c);
  //fprintf(stdout,"residual: %f\n",r1*r1+b*r1+c);


  b=a3/2.+sqrt(a3*a3/4.+u1-a2);
  c=u1/2.-sqrt(u1*u1/4.-a0);
  fprintf(stdout,"Solved this quadratic: %f %f\n",b,c);
  fprintf(stdout,"residual: %f\n",r1*r1+b*r1+c);

  r2=quadsolve(1.,b,c,&dum,0);

  fprintf(stdout,"r1,r2: %f %f\n",r1,r2);
  test=r1*r1*r1*r1 + a3*r1*r1*r1 + a2*r1*r1 + a1*r1 + a0;
  fprintf(stdout,"Residual for r1: %f\n",test);
  test=r2*r2*r2*r2+a3*r2*r2*r2+a2*r2*r2+a1*r2+a0;
  fprintf(stdout,"Residual for r2: %f\n",test);
*/

   double R2=a3*a3/4.-a2+u1;
   if (R2 <= 0)
    return(-832.);
   double R=sqrt(R2);
   double t1=3.*a3*a3/4.-R2-2.*a2;
   double t2=.25*(4.*a3*a2-8.*a1-a3*a3*a3)/R;
   double D2=t1+t2;
   double E2=t1-t2;
  if (D2 < 0){
    r1=-HUGE;
    r2=-HUGE;
   }
   else{
    r1=-a3/4.+R/2+sqrt(D2)/2.;
    r2=-a3/4.+R/2-sqrt(D2)/2.;
   }
   if (E2 < 0){
    r3=-HUGE;
    r4=-HUGE;
   }
   else{
    r3=-a3/4.-R/2+sqrt(E2)/2.;
    r4=-a3/4.-R/2-sqrt(E2)/2.;
   }

/*  if (debug){
   fprintf(stdout,"r1: %f %f\n",r1,(4*r1*r1*r1 + 3*a3*r1*r1 + 2*a2*r1 + a1)*a4);
   fprintf(stdout,"r2: %f %f\n",r2,(4*r2*r2*r2 + 3*a3*r2*r2 + 2*a2*r2 + a1)*a4);
   fprintf(stdout,"r3: %f %f\n",r3,(4*r3*r3*r3 + 3*a3*r3*r3 + 2*a2*r3 + a1)*a4);
   fprintf(stdout,"r4: %f %f\n",r4,(4*r4*r4*r4 + 3*a3*r4*r4 + 2*a2*r4 + a1)*a4);
  }
*/


 double retroot=HUGE,vattc;
  if (r1>0 && r1 < retroot){
    vattc=(4*r1*r1*r1 + 3*a3*r1*r1 + 2*a2*r1 + a1)*a4;
    if (vattc < 0) 
     retroot=r1;
  }
  if (r2>0 && r2 < retroot){
    vattc=(4*r2*r2*r2 + 3*a3*r2*r2 + 2*a2*r2 + a1)*a4;
    if (vattc < 0) 
      retroot=r2;
  }
  if (r3>0 && r3 < retroot){
    vattc=(4*r3*r3*r3 + 3*a3*r3*r3 + 2*a2*r3 + a1)*a4;
    if (vattc < 0) 
     retroot=r3;
  }
  if (r4>0 && r4 < retroot){
    vattc=(4*r4*r4*r4 + 3*a3*r4*r4 + 2*a2*r4 + a1)*a4;
    if (vattc < 0) 
     retroot=r4;
  }
  if (HUGE == retroot) 
    retroot *= -1;

  return(retroot);

}


/*Solve the Quartic z^4 + a3 z^3 + a2 z^2 + a1 z +a0 See page 17 Abramowitz
  & Stegun
double quartsolve(double a0,double a1,double a2,double a3)
{
  double u1,b,c,cc2,cc1,cc0,dum;
  double r1,r2,u2,u3;
  int count=0;
  First we solve a cubic equation
  cc2=-a2;
  cc1=(a1*a3-4.*a0);
  cc0=-(a1*a1+a0*a3*a3-4.*a0*a2);
  u1=cubesolve(cc2,cc1,cc0,&u2,&u3);

//  printf("The roots: u1=%f u2=%f u3=%f\n",u1,u2,u3);

  if ((u2 != 444.) || (u3 != 444.)){
    if ((u1 + .25*a3*a3 - a2 > 0.) && (.25*u1*u1 - a0 >0.)) {
      u1=u1;
      count=count+1;
    }
    if ((u2 + .25*a3*a3 - a2 > 0.) && (.25*u2*u2 - a0 >0.)){
      u1=u2;
      count=count+1;
    }
    if ((u3 + .25*a3*a3 - a2 > 0.) && (.25*u3*u3 - a0 >0.)){
      u1=u3;
      count=count+1;
    }
  }

//  printf("how many work? %i \n",count);

//  assert(count==1); 

//  printf("The one that works is: %f\n",u1);
//  printf("coefficients: a0=%f a1=%f a2=%f a3=%f\n",a0,a1,a2,a3);

  Now we have 2 quadratic equations
  b=a3/2.-sqrt(a3*a3/4.+u1-a2);
  c=u1/2.+sqrt(u1*u1/4.-a0);

//  printf("Quartsolve. a=1. b=%f c=%f\n",b,c);

  r1=quadsolve(1.,b,c,&dum,0);
  b=a3/2.+sqrt(a3*a3/4.+u1-a2);
  c=u1/2.-sqrt(u1*u1/4.-a0);
 
//  printf("Quartsolve. a=1. b=%f c=%f\n",b,c);

  r2=quadsolve(1.,b,c,&dum,0);

//  printf("Quartsolve: r1=%f r2=%f\n",r1,r2);

  And return the smallest positive root (time)
  if (((r1 > 0.) && (r1 < r2)) || ((r1 > 0.) && (r2 < 0)))
    return(r1);
  if (((r2 > 0.) && (r2 < r1)) || ((r2 > 0.) && (r1 < 0.)))
    return(r2);
  return (-832.);
}
*/












