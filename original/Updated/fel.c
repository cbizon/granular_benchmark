#include "main.h"
#include "fel.h"
#include <stdlib.h>
#include <iostream>
using namespace std;
#include <stdio.h>
#include <math.h>
#include <assert.h>

extern int fel[];
extern P_DATA p[];



int fel_neighbor( int a ) {
if (a == 0)
  return 0;
else {
  if (a % 2)
    return(a+1);
  else 
    return(a-1);
};
}

int fel_parent( int a ) {
  if ( a == 0 ) 
    return(-1);
  else
    return((a-1)/2);
}

/* evaluates (p[a].cl->time < p[b].cl->time) */
/* checks for NULL collisions and sets time = +inf if NULL */
 
inline int fel_min( int a, int b ) {
  double Atime = (p[a].cl != NULL) ? p[a].cl->time : HUGE;
  double Btime = (p[b].cl != NULL) ? p[b].cl->time : HUGE;
  return(Atime < Btime);
} 

void fel_sort(int debug) {
  for(int i=0;i<NP;i+=2) {
    int TheLeaf = (i / 2) + (NP/2) - 1; 
    int PNeighbor = (i % 2) ? (i-1) : (i+1);
    int NewVal = (fel[TheLeaf] = fel_min(i,PNeighbor) ? i : PNeighbor);  
  }
   {for(int i=NFEL-1;i>0;i-=2) {
    int TheParent = fel_parent(i);
    int TheNeighbor = fel_neighbor(i);
    int TheMin = fel_min( fel[TheNeighbor], fel[i] ) ? fel[TheNeighbor] : fel[i];
    fel[TheParent] = TheMin;
  };
  }
}


void tree_resort( int a ) {
  int TheLeaf = (a / 2) + (NP/2) - 1; 
  int PNeighbor = (a % 2) ? (a-1) : (a+1);
  if (fel_min(fel[PNeighbor],fel[a]) && (fel[TheLeaf] == PNeighbor))
    return;
  else {
    fel[TheLeaf] = fel_min(a, PNeighbor) ? a : PNeighbor;
    fel_resort(TheLeaf);
  }
}

/*int fel_resort( int a ) {
  int TheParent = fel_parent(a);
  if(TheParent != -1) {
    int TheNeighbor = fel_neighbor(a);
    //cout << TheNeighbor << endl;
    int NewValue = fel_min(fel[a], fel[TheNeighbor]) ? a : TheNeighbor;
    //cout << "int fel_resort(" << a << "): Neighbor=" << TheNeighbor << "; Parent=" << TheParent << "; NewValue=" << NewValue << endl;
    //cout << "int fel_resort(" << a << "): fel[Parent]=" << fel[TheParent] << "; fel[Neighbor]=" << fel[TheNeighbor] << "; fel[a]=" << fel[a] << endl;
    if (NewValue != a) { 
      //cout << "a loses -- end." << endl;
      return 0;
    }
    else {  
      //cout << "a wins -- continue." << endl;
      fel[TheParent] = NewValue;
      fel_resort(TheParent);
    }
  }
}*/

void fel_resort( int a ) {
  int TheLeaf = (a/2) + NP/2 -1;
  int PNeighbor = (a % 2) ? (a-1) : (a+1);
  int NewVal = (fel[TheLeaf] = fel_min(a,PNeighbor) ? a : PNeighbor);
  int TheParent,TheNeighbor,TheMin;

  for (int i = 0;i<NLEVELS;i+=1) { 
     TheParent = fel_parent(TheLeaf);
     TheNeighbor=fel_neighbor(TheLeaf);
     TheMin = fel_min(fel[TheNeighbor],fel[TheLeaf]) ? fel[TheNeighbor] : fel[TheLeaf];
     fel[TheParent] = TheMin;
     TheLeaf = TheParent;
  } 
  assert (TheLeaf == 0);
}


//int fel_print() {
//  int TheCount = 0;
//  int TreeDepth = (int) ((float) log(NP)/ (float) log(2));
//  for(int i=0;i<TreeDepth;i++) {
//    int TheBreadth = (int) pow(2,i);
//    for(int j=0;j<TheBreadth;j++)
//      printf("%5d ",fel[TheCount++]);
//    printf("\n"); }
//}
