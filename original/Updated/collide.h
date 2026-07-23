double dot(PVECTOR,PVECTOR);
double ballball(int,int);
void ballwall(int,int,int*);
PVECTOR cross(PVECTOR,PVECTOR);
void statstat(int);
void vwall(int,int);
void evolve(int,double,int);
void g_evolve(double,int);
double gasdev(void);
double zdev(void);
void thermalize(int,int);
void feedback(double,int,int);
void pickn(int*,int,int,int);
#if THERMAL4 == 1
void fluctforce(int,int);
#endif
