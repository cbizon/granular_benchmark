
struct CellNode {
  int p;
  int Valid;
  struct CellNode *next;
};

typedef CellNode CellNodeType;

typedef CellNode* CellNodePtr;

class CellSet {
private:
  int iNumMembers;
  CellNodePtr CellContents;
public:
  CellSet();
  void add(int item);
  void remove(int item);
  void removeall();
  int members(int *TheMembers);
  void display();
  void display(char *str);
};






