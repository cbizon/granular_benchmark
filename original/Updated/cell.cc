#include <stdlib.h>
#include <iostream>
using namespace std;
#include <stdio.h>
#include <assert.h>
#include "cell.h"

CellSet::CellSet() {
  iNumMembers = 0;
  CellContents = NULL;
}

/* CellSet::DeleteNodes(CellNodePtr ToDelete) {
  if (ToDelete != NULL) {
    CellDeleteNodes(ToDelete->next);
    Delete ToDelete;
  } 
} */

/* CellSet::~CellSet() {
  DeleteNodes(CellContents);
  CellContents = NULL;
  iNumMembers = 0;
} */


void CellSet::add(int item) {
  if (CellContents == NULL) {
    CellContents = new CellNodeType;
    if (CellContents == NULL) {
      fprintf(stdout,"Death in CellSet::add\n");
      fprintf(stdout,"CellContents = NULL\n");
      assert(CellContents != NULL);}
    CellContents->p = item;
    CellContents->Valid = 1;
    CellContents->next = NULL;
  }
  else {
    CellNodePtr TmpPtr = CellContents;
    while ((TmpPtr->next != NULL) && (TmpPtr->Valid == 1))
      TmpPtr = TmpPtr->next;
    if (TmpPtr->Valid == 0) {
      TmpPtr->p = item;
      TmpPtr->Valid = 1;
    } 
    else {
      TmpPtr->next = new CellNodeType;
      if (TmpPtr->next == NULL){
        fprintf(stdout,"Death in CellSet::add\n");
        fprintf(stdout,"TmpPtr->next==NULL\n");
        assert(TmpPtr->next != NULL);}
      TmpPtr = TmpPtr->next;
      TmpPtr->p = item;
      TmpPtr->Valid = 1;
      TmpPtr->next = NULL;
    }
  }
  iNumMembers += 1;
}

void CellSet::display(char *str) {
  CellNodePtr TmpPtr = CellContents;
/*  int i = 0;
  while (TmpPtr != NULL) {
    if (TmpPtr->Valid) {
      sprintf(str + i,"%4d",TmpPtr->p);
      i += 5;
    }
    TmpPtr = TmpPtr->next;
  }
  if (i == 0)
    sprintf(str,"%40s","fuck "); */
    sprintf(str,"%40s","fuck ");
}

void CellSet::display() {
  CellNodePtr TmpPtr = CellContents;
  while (TmpPtr != NULL) {
    if (TmpPtr->Valid)
      cout << " " << TmpPtr->p;
    else
      cout << " i";
    TmpPtr = TmpPtr->next;
  }
  cout << endl;
}

int CellSet::members(int *TheMembers) {
  if (iNumMembers == 0)
    return(0);
  if (iNumMembers == -1)
    return(-99);
  else {
    CellNodePtr TmpPtr = CellContents;
    int TheCounter = 0,i=0;
    while (TmpPtr != NULL) {
      if (TmpPtr->Valid)
	TheMembers[i++] = TmpPtr->p;
      TmpPtr = TmpPtr->next;
    }
    if (iNumMembers != i) {
      fprintf(stderr,"FATAL ERROR in Cell::Members\n\tiNumMebers = %d, i = %d\
n",iNumMembers,i);
      fprintf(stdout,"Death in CellSet::members\n");
      fprintf(stdout,"iNumMembers: %d i:%d\n",iNumMembers,i);
      fprintf(stdout,"The crappy particle: %d\n",CellContents->p);
      assert(iNumMembers == i);}
    return(iNumMembers);
  }
}

//This is the old remove.  It works, but uses too much memory.
/*CellSet::remove(int item) {
  CellNodePtr TmpPtr = CellContents;
  int NotFound = 1;
  while ((TmpPtr != NULL) && NotFound) {
    if (TmpPtr->Valid)
      if (TmpPtr->p == item){
	TmpPtr->Valid = 0;
	NotFound = 0;
	iNumMembers -= 1;
         if ( iNumMembers < 0 )  {
           fprintf(stdout,"Cell is too empty\n");
           fprintf(stdout,"Took out particle %d\n",item);
           assert(1 == 0);}
      }
    TmpPtr = TmpPtr->next;
  }
}*/

void CellSet::remove(int item) {
  CellNodePtr OldPtr = CellContents;
  CellNodePtr NewPtr = CellContents;
  int NotFound = 1;
  while ((NewPtr != NULL) && NotFound) {
    if (NewPtr->p == item){
      NotFound = 0; 
      iNumMembers -= 1;
      if (NewPtr == CellContents) {
        CellContents = NewPtr->next;
        delete NewPtr;        
       }
      else {
       OldPtr->next = NewPtr->next;
       delete NewPtr;
      } 
     }
    else {
     OldPtr = NewPtr;
     NewPtr = NewPtr->next;
    }
  }
}

void CellSet::removeall() {
  CellNodePtr TmpPtr = CellContents;
  while (TmpPtr != NULL) {
    TmpPtr->Valid = 0;
    TmpPtr = TmpPtr->next;
  }
  iNumMembers = 0;
}

/* int main() {
  CellSet TheSet[50][50][50];
  int SetCount[100];
  int choice = 0, TheEntry = 0, NumRet = 0;
  while ((TheEntry != -1) && (choice != -1)) {
    cout << "1 - print set\n";
    cout << "2 - add to set\n";
    cout << "3 - remove from set\n";
    cout << "4 - get set\n";
    cout << "> ";
    cin >> choice;
    switch (choice) {
    case 1:
      TheSet[1][1][1].display();
      break;
    case 2:
      cin >> TheEntry;
      if (TheEntry >= 0)
	TheSet[1][1][1].add(TheEntry);
      break;
    case 3:
      cin >> TheEntry;
      if (TheEntry >= 0)
	TheSet[1][1][1].remove(TheEntry);
      break;
    case 4:
      NumRet = TheSet[1][1][1].members(SetCount);
      cout << "Returned " << NumRet << " elements.\n";
      for(int i=0;i<NumRet;i++)
	cout << SetCount[i] << "  ";
      cout << endl;
      break;
    }
  }
}

*/
