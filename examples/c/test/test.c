#include "test.h"
#define xyz
#ifdef xyz

int arr[10];

int hello(int* input, BYTE_8* output, int* mixed){
    arr[0] = 0;
    int temp = *input+3 + *mixed;
    *output += 2;
    *mixed += 4;
    return temp;
}
#endif

