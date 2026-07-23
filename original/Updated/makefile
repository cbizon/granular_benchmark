SOURCES = clist.c fel.c plist.c collide.c detect.c stat.c cell.cc files.c \
xmain.c
OBJECTS = clist.o fel.o plist.o collide.o detect.o stat.o cell.o files.o \
xmain.o




CFLAGS = -I/usr/include/g++ -O5

all : $(OBJECTS) $(X11OBJ)
	g++ $(CFLAGS) $(OBJECTS) $(X11OBJ) -lm $(LFLAGS)

x : $(OBJECTS) $(X11OBJ) 
	g++ $(CFLAGS) $(OBJECTS) -lm 

gl : $(OBJECTS) $(GLOBJ)
	g++ $(CFLAGS) $(OBJECTS) $(GLOBJ) -lm -lgl_s

clist.o : clist.c clist.h main.h
	g++ -c $(CFLAGS) clist.c



fel.o : fel.c fel.h main.h
	g++ -c $(CFLAGS) fel.c

plist.o : plist.c plist.h main.h
	g++ -c $(CFLAGS) plist.c

collide.o : collide.c collide.h main.h
	g++ -c $(CFLAGS) collide.c

detect.o : detect.c detect.h main.h
	g++ -c $(CFLAGS) detect.c	

cell.o : cell.cc cell.h main.h
	g++ -c $(CFLAGS) cell.cc

main.o : main.c main.h
	g++ -c $(CFLAGS) main.c

files.o : files.c files.h main.h
	g++ -c $(CFLAGS) files.c

xmain.o : xmain.c main.h
	g++ -c $(CFLAGS) xmain.c

stat.o : stat.c stat.h main.h
	g++ -c $(CFLAGS) stat.c

clean :
	touch main.h
	rm *.o


