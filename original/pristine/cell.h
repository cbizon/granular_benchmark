
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
  add(int item);
  remove(int item);
  removeall();
  int members(int *TheMembers);
  display();
  display(char *str);
};







