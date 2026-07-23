#include <stdlib.h>
#include <iostream>
using namespace std;
#include <stdio.h>
#include "main.h"

extern double Gtime;
extern P_DATA p[];
extern long NumBallColl;
extern long NumWallColl;
extern ParamStructPtr TheParams;

void do_stats() {
  /* calculate total energy in system */
  double Total_Energy = 0.0;
  for(int i=0;i<TheParams->nball;i++) 
    Total_Energy += p[i].vel.x * p[i].vel.x + p[i].vel.y * p[i].vel.y + p[i].vel.z * p[i].vel.z;
  
}
