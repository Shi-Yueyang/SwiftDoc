#include "test.h"
#define xyz
#ifdef xyz

int arr_in[10];
int arr_out[10];
int arr_mix[10];;

int hello(int* input, BYTE_8* output, int* mixed){
    arr_in[0] = 0;
    arr_mix[0] = 0;
    int temp = *input+3 + *mixed + arr_out[0]+arr_mix[0];
    *output += 2;
    *mixed += 4;
    return temp;
}
#endif

