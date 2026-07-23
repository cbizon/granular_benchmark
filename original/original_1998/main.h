#define RUN "T1000"
#define RANDOM 16532
#define FREQUENCY (1./sqrt(0.95))
#define NMOV 2116
/* sand.h -- data structures for the sand simulation experiment */

#define DIMENSION 2 /*Dimensions in which the particles move*/
#define QUASI 0
#define SIDESMOVE 0
#define DENSIFY 1

#define START 1          /*If START = 0, start with random beginning*/
#define OLDRUN "../start/nu6"
                        /*If START = 1, restart from OLDRUN*/


#define STATS 10.  /*Number of Writes/Period for Stats and Fields*/
#define FIELDS .5
#define PRESSURE 1

#define QFLOATS 0 /*If 0, write fields and stats as floats
                    If 1, write fields and stats as doubles
                    balls and restart are always written double.*/

#define ROOTACC (1.0e-9)
#define PDIAM .95      /* default, initial particle diameter */
#define PRAD  (PDIAM/2)  /* particle radius */
#define PDISP 0.01        /*Polydispersion*/
#define BSIZE 95  	/* box side length, determines number of virtual
			cells */

#define GSIZE (BSIZE+2)  /* actual number of virtual cells is greater than
			box size.  Empty layer of virtual cells surrounding
			outside walls */

#define YBSIZE 50 
#define ZBSIZE 50
#define YGSIZE (YBSIZE+2)
#define ZGSIZE (ZBSIZE+2)

#if DIMENSION == 2
#define XBSIZE 1
#define XGSIZE 3
#else
#define XBSIZE 95
#define XGSIZE 97
#endif

#define G 1.0
#define GRAV 1
#define GRAVDIM 2

#define RESTTYPE 1 	/* For RESTTYPE 0, use a constant coefficient of
                            restitution for velocities greater than 
                            sqrt(0.02 * g * pdiam), and 1 below this.
                           For RESTTYPE 1, use a constant coefficent of
                            restititution for velocities greater than
                            sqrt(0.2*g*pdiam), and 1-RSLOPE*v^(3/4) below this.  
                            RSLOPE is chosen so that e=ballrest at vmin */

#define MAX_VEL 115.0        /* maximum initial random velocity */
#define ZEROMOM 1
#define THERMAL 0
#define THERMAL2 0
#define THERMAL3 0
#define THERMAL4 1
#define CONSERVE 0
#define SLIP 1
#define INSET 2*0.95
#define BOTT -1.  /*The desired average square velocity*/
#define TOPT -1.
#define MIDT 1000.0
#define GRADIENT 2
#define SIGB sqrt(BOTT)/*The standard deviations for velocity calcs*/
#define SIGT sqrt(TOPT)
#define SIGM sqrt(MIDT)
#define RESTITUTION  0.7  /* coefficient of restitution for collisions */
#define WALLREST 1.0
#define BALLREST 0.7

#define ROTATIONS 1
#if ROTATIONS == 1
#define BETA0BALL .35
#define BETA0WALL .35
#define BALLMU 0.0
#define WALLMU 0.0
#else
#define BALLFRICTION 1
#define BALLMU 0.5
#define WALLFRICTION 1
#define WALLMU 0.1
#endif

#define GAMMASWEEP 0 /*If GAMMASWEEP = 0 run at fixed Gamma until TFINAL*/
                     /*If GAMMASWEEP = 1 sweep GAMMA from GAMMAINIT to 
                          GAMMAFINAL in steps of GAMMASTEP, staying at each
                          GAMMA for GAMMATIME periods. In this case, GAMMA 
                          should be set to the MAXIMUM of the two. Also,
                          TFINAL should be 
                          GAMMATIME*((GAMMAINIT-GAMMAFINAL)/GAMMASTEP+1) */

#define GAMMA 0.00
#define TFINAL 1e5  /*Length of simulation in Periods*/

#define GAMMAINIT 3.0
#define GAMMAFINAL 2.0
#define GAMMASTEP -1.0
#define GAMMATIME 5


#define PERIOD 1./FREQUENCY

#define PLATEMOVE -1  /*If PLATEMOVE == 0, use a parabolically forced base*/
                    /*If PLATEMOVE == 1, use a sinusoidally forced base*/
                     /*If PLATEMOVE == -1, dont move at all*/
#if PLATEMOVE == 0
#define AMPL GAMMA*PERIOD*PERIOD/32.
#else if PLATEMOVE == 1
//#define PI acos(-1.)
#define OMEGA (2.*PI*FREQUENCY)        /*Angular Frequency*/
#if GAMMASWEEP == 0
#define AMPL (GAMMA/(OMEGA*OMEGA))      /*Amplitude*/
#if PLATEMOVE == -1
#define TIMEONE 2.5*PERIOD
#else
#if GRAV == 1
#define TIMEONE (asin(1./GAMMA)/OMEGA)  /*Time at which a=1, to save time
					in calculateing wall collisions*/
#else
#define TIMEONE 0.
#endif
#endif
#else if GAMMASWEEP == 1
#define AMPL (GAMMAINIT/(OMEGA*OMEGA))
#define TIMEONE (asin(1./GAMMAINIT)/OMEGA)
#endif 
#endif

#define PERIODIC 3    /*0: NOT PERIODIC*/ 
                      /*1: PERIODIC in X and Y */
                      /*2: PERIODIC in X */
                      /*3: PERIODIC in X and Y and Z*/

#define OSC 0
#define WALLVEL 0.6
#define WPHI 10

#define FOLLOW 0	/* 1 -- follow Particle THIS */
                        /* 0 -- Dont follow Particle THIS */
#define THIS 141

#define ZZERONORM 0

#define DEBUG_LVL 0	/* the debugging output level: 			*/
			/* 0 -- no debugging output			*/
			/* 1 -- program flow only (main procedures)	*/
                        /* 2 -- intermediate results	*/
			/* 3 -- ?? */

#define NP 8192  	/* maximum total number of particles */
#define NLEVELS 12              /* log_2(NP)-1 : number of FEL tests */
#define NWALL 6                  /* initial number of wall particles */
#define NSTAT 3                  /* initial number of statistical events */
#define NVWALL 6		/* number of virtual walls */
#if THERMAL == 1
#define NUMTHERM 2		/* number of thermal walls*/
#define NJUNK (NP-NWALL-STAT-NVWALL-NMOV-NUMTHERM)
#else
#define NJUNK (NP-NWALL-STAT-NVWALL-NMOV)
#endif
#define NFEL (NP - 1)            /* number of FEL leaf nodes */


#define FMOV    0                    /* index of first moving particle */
#define LMOV    (NMOV-1)             /* index of last moving particle */
#define FWALL   (LMOV+1)             /* index of first wall */
#define LWALL   (FWALL + NWALL - 1)  /* index of last wall */
#define FVWALL  (LWALL + 1)          /* index of first virtual wall */
#define LVWALL  (FVWALL +NVWALL -1)  /* index of last virtual wall */
#define PLUSX   FVWALL               /* index of positive x virutal wall */
#define NEGX    (PLUSX + 1)          /* index of negative x virtual wall */
#define PLUSY   (NEGX + 1)           /* index of positive y virtual wall */
#define NEGY    (PLUSY + 1)          /* index of negative y virtual wall */
#define PLUSZ   (NEGY + 1)           /* index of positive z virtual wall */
#define NEGZ    (PLUSZ + 1)          /* index of negative z virtual wall */
#define FSTAT   (LVWALL + 1)         /* index of first stat event */
                                     /* FSTAT: Xupdate, Collect Stats, Check
                                               for escapes */
                                     /* FSTAT + 1: Move Plate */
                                     /* FSTAT + 2: Write Particle Info */ 
#define LSTAT   (FSTAT + NSTAT - 1)  /* index of last stat event */
#if THERMAL == 1
#define PTHERM  (LSTAT + 1)
#define NTHERM  (PTHERM + 1)
#define FJUNK   (NTHERM + 1)
#else
#define FJUNK   (LSTAT + 1)
#endif
#define LJUNK   (FJUNK + NJUNK - 1)

#define DWIDTH 400
#define DHEIGHT 400

#define STWIDTH 150
#define STHEIGHT 130

#define WOFFSET 0.001	/* distance real walls are set in from virtual walls */
#define TMAX  (TFINAL * PERIOD) /*Time of simulation in sim. units*/
#define TIMESTEP PERIOD/STATS

typedef struct Pvector {
  double x,y,z;
} PVECTOR;

typedef struct Cvector {
  int x,y,z;
} CVECTOR;

typedef struct c_data {	/* struct containing collision info */
  double time;		/* time of collision */
  int b;		/* other particle b */
  int cb;		/* number of collisions of b at scheduling */
  c_data *cnext;
} C_DATA;

typedef struct p_data {	/* struct containing particle data */
  int pty;
#ifdef GRAVDIM
  PVECTOR gvec;
  double lgt;
#endif
  double g;
  double diam;
  PVECTOR loc;  
  PVECTOR vel;	/* location and velocity of particle */
  PVECTOR norm; /* normal vector in case of wall */
  CVECTOR cell;
  double time;  /* particle local time */
  long c;  /* number of collisions suffered */
  int wallcalc;
  C_DATA *cl;
#if ROTATIONS == 1
  PVECTOR ome;
#endif
} P_DATA;

typedef struct ParamStruct {
#if ((WALLFRICTION != 0) || (ROTATIONS == 1))
  double wmu;
#endif
#if ((BALLFRICTION != 0) || (ROTATIONS == 1))
  double bmu;
#endif
#if ROTATIONS == 1
  double beta0w;
  double beta0b;
#endif
  int a,b;
  double etime,pdiam,DiamStep;
  int update;
  int NumVwall;
  int DoSimulate;
  int StopOnError;
  int Initialized;
  int ErrorCheck;
  int pclist;
  int Restitution;
  double BallRest, WallRest;
  int Verify;
  int DrawGrid;
  int CPUStat;
  double CPUTime;
  double Period;
  double Ampl;
  double WallVel;
  double Omega;
  double osc;
  double wphi;
  int View3D;
  double g;
  int glinit;
  double TimeOne;
  int nball,maxball,nwall,nvwall,fball,lball,fwall,lwall,fvwall,lvwall,fstat,nstat,lstat,fjunk,njunk,ljunk,plusx,negx,plusy,negy,plusz,negz;
  #if THERMAL == 1  || THERMAL2 == 1  || THERMAL3 == 1 || THERMAL4==1
  double sigb,sigt,sigm;
  int ntherm,ptherm;
  #endif
};

typedef struct ParamStruct* ParamStructPtr;

typedef double C_TIME;

/* Function prototypes
*/

void pty_print(int);
void p_print(int);
void c_print(int);
void std_box();
double get_ctime( int a );
void cl_sort( void );
int c_add( int, int, double );
int cl_print();
int new_collision();
int fel_change();
int fel_neighbor( int );
int fel_parent( int );
int fel_sort( int );
int tree_resort( int );
int fel_min( int, int ); // returns index of minimum time fel entry
int lel_kill( int );
int lel_destroy( int );
double cdetect( int, int );
int c1detect(int, int, int);
double c3detect(int,int);
double cwdetect(int,int);
int simulate(int step);
int SetupXWindows(int,char**);
int XMainLoop();
int MainLoop();
void usage();
int get_options(int,char**);
int grid_destroy();
int recalc_params();
int validate(int);
int cxdetect(int,int);
int cydetect(int,int);
int czdetect(int,int);
double zdetect(int,int);
int XStatUpdate(int);
void the_gl_init();
void the_gl_close();

#define DASH10 "- - - - - "
#define DASH20 "- - - - - - - - - - " 
#define DASH30 "- - - - - - - - - - - - - - - "
#define DASH40 "- - - - - - - - - - - - - - - - - - - - "
#define DASH50 "- - - - - - - - - - - - - - - - - - - - - - - - - "
#define DASH60 "- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - "
#define DASH70 "- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - "
#define DASH80 "- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - "
#define SEP10  "----------"
#define SEP20  "--------------------"
#define SEP30  "------------------------------"
#define SEP40  "----------------------------------------"
#define SEP50  "--------------------------------------------------"
#define SEP60  "------------------------------------------------------------"
#define SEP70  "----------------------------------------------------------------------"
#define SEP80  "--------------------------------------------------------------------------------"

#define SPHERE 0
#define WALL 1
#define VWALL 2
#define STAT 3
#define JUNK 4
#define THERM 5
void printit();

#if TONLY == 1
typedef struct slab {
  int numin;
  double vzbar;
}; 
#endif
