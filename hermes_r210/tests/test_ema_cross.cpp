// Testa a decisao pura do Caso 9 (filtro de cruzamento EMA5/EMA21). Nao e simulacao de mercado.
#include <cmath>
#include <cassert>
#include <algorithm>
#include <iostream>
#include <vector>
#include <limits>
template<class A,class B> double MathMax(A a,B b){return std::max(double(a),double(b));}
template<class A,class B> double MathMin(A a,B b){return std::min(double(a),double(b));}
double MathAbs(double x){return std::abs(x);} double MathFloor(double x){return std::floor(x);}
double MathCeil(double x){return std::ceil(x);} double MathRound(double x){return std::round(x);}
bool MathIsValidNumber(double x){return std::isfinite(x);}
#include "Core_Runtime.inc"
#include "../src/EMACrossCore.mqh"

int main(){
 const double nan=std::numeric_limits<double>::quiet_NaN();
 int out=0;

 // 1. Cruzamento fresco de compra: alinhada agora (idx0), cruzou no meio da janela (idx2).
 { std::vector<double> e5{10.2,10.2,9.9,9.9}, e21{10.0,10.0,10.0,10.0};
   assert(EMACrossGate(1,e5,e21,4,out)==EMAX_READY && out==1); }

 // 2. Cruzamento fresco de venda (espelho): alinhada agora (idx0<idx21), cruzou no meio (idx2).
 { std::vector<double> e5{9.8,9.8,10.1,10.1}, e21{10.0,10.0,10.0,10.0};
   assert(EMACrossGate(-1,e5,e21,4,out)==EMAX_READY && out==-1); }

 // 3. Alinhamento ANTIGO, sem cruzamento dentro da janela -> NAO e um "cruzamento".
 { std::vector<double> e5{10.2,10.3,10.4,10.5}, e21{10.0,10.0,10.0,10.0};
   assert(EMACrossGate(1,e5,e21,4,out)==EMAX_NONE && out==0); }

 // 4. Nao alinhada AGORA (mesmo com cruzamento antigo la atras) -> nao confirma o lado.
 { std::vector<double> e5{9.9,10.5,10.5,10.5}, e21{10.0,10.0,10.0,10.0};
   assert(EMACrossGate(1,e5,e21,4,out)==EMAX_NONE); }

 // 5. Cruzamento exatamente na borda mais antiga da janela (ultimo indice) -> inclusivo.
 { std::vector<double> e5{10.2,10.3,10.4,9.9}, e21{10.0,10.0,10.0,10.0};
   assert(EMACrossGate(1,e5,e21,4,out)==EMAX_READY && out==1); }

 // 6. Toque exato (igualdade) conta como lado oposto/cruzamento.
 { std::vector<double> e5{10.2,10.0,10.0,10.0}, e21{10.0,10.0,10.0,10.0};
   assert(EMACrossGate(1,e5,e21,4,out)==EMAX_READY); }
 { std::vector<double> e5{9.8,10.0,10.0,10.0}, e21{10.0,10.0,10.0,10.0};
   assert(EMACrossGate(-1,e5,e21,4,out)==EMAX_READY); }

 // 7. Lado invalido.
 { std::vector<double> e5{10.2,9.9,9.9,9.9}, e21{10.0,10.0,10.0,10.0};
   assert(EMACrossGate(0,e5,e21,4,out)==EMAX_DATA && out==0); }

 // 8. Janela pequena demais (n<2).
 { std::vector<double> e5{10.2}, e21{10.0}; assert(EMACrossGate(1,e5,e21,1,out)==EMAX_DATA); }

 // 9. Dados invalidos (NaN) em qualquer ponto da janela, dos dois lados.
 { std::vector<double> e5{10.2,nan,9.9,9.9}, e21{10.0,10.0,10.0,10.0};
   assert(EMACrossGate(1,e5,e21,4,out)==EMAX_DATA); }
 { std::vector<double> e5{10.2,10.3,9.9,9.9}, e21{10.0,10.0,nan,10.0};
   assert(EMACrossGate(1,e5,e21,4,out)==EMAX_DATA); }

 std::cout<<"Cruzamento EMA5/21 (Caso 9): compra, venda, alinhamento antigo sem cruzar, "
            "desalinhado agora, borda da janela, toque exato, lado/janela/dados invalidos passaram.\n";
 return 0;
}
