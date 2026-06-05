void braces_inbalance_without_macro()
{

#ifdef SOME_MACRO
    if(1){
#endif

#ifdef OTHER_MACRO
    if(1){
#endif
        printf("");
    }
}

void func_after(){}

void another_braces_inblance()
{
#ifdef M1
    if(){

#endif
    }
}