#include "test.h"
#define xyz
#define DIS int
#ifdef xyz

int arr_in[10];
int arr_out[10];
int arr_mix[10];

int input_direction(int* input, BYTE_8* output, int* mixed){
    arr_in[0] = 0;
    arr_mix[0] = 0;
    int temp = *input+3 + *mixed + arr_out[0]+arr_mix[0];
    *output += 2;
    *mixed += 4;
    int c = (DIS)(temp);
    return temp;
}


#endif


