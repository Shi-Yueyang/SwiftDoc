void braces_inbalance_without_macro()
{

#ifdef MA
    while(1){
        if(1){}
#endif
#ifdef MB
    {
        if(1){}
#endif
        printf("");
    }

    
}

void func_after(){
    if(1){
        if(1){
            switch(a){
                default:
                break;
            }
        }
    }
}

void another_braces_inblance()
{
#ifdef M1
    if(){

#endif
    }
}