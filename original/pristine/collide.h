double dot(PVECTOR,PVECTOR);
double ballball(int,int);
int ballwall(int,int,int*);
PVECTOR cross(PVECTOR,PVECTOR);
int statstat(int);
int vwall(int,int);
int evolve(int,double,int);
int g_evolve(double,int);
double gasdev(void);
double zdev(void);
void thermalize(int,int);
void feedback(double,int,int);
void pickn(int*,int,int,int);
#if THERMAL4 == 1
void fluctforce(int,int);
#endif
