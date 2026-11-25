// Deterministic compatibility checks on recorded observation streams.
#include <iostream>
#include <sstream>
#include <iomanip>
#include <stdexcept>
#define aspect legacy_aspect
#include "pbr_policy_legacy.h"
#undef aspect
#undef aspect_pbr_policy_h
#include "../pbr_policy.h"

void require(bool ok, const std::string &what)
{ if (!ok) throw std::runtime_error(what); }

void compare(const long index)
{
  const auto &a=legacy_aspect::PBR::state();
  const auto &b=aspect::PBR::state();
  require(a.rebuild==b.rebuild && a.heldBase==b.heldBase && a.runAge==b.runAge &&
          a.est==b.est && a.avg==b.avg && a.levels==b.levels && a.dN==b.dN &&
          a.rSamples==b.rSamples && a.rMed==b.rMed && a.rLast==b.rLast &&
          a.tot==b.tot && a.acc==b.acc && a.accn==b.accn && a.nDone==b.nDone &&
          a.nRebuilds==b.nRebuilds && a.nForced==b.nForced && a.dSrc==b.dSrc,
          "legacy mismatch at event "+std::to_string(index));
}

void clearStates(const char *cond)
{
  legacy_aspect::PBR::state()=legacy_aspect::PBR::State();
  aspect::PBR::state()=aspect::PBR::State();
  setenv("PBR_POLICY","online",1); setenv("PBR_BASE","100",1);
  setenv("PBR_COND",cond,1); unsetenv("PBR_LOG"); unsetenv("PBR_UNIT");
}

void solve(double n, double setup=1.)
{
  auto &s=aspect::PBR::state();
  if (s.rebuild) aspect::PBR::noteBuildTime(setup);
  aspect::PBR::noteSolve(static_cast<unsigned long>(n),n);
  aspect::PBR::noteRatio();
}

void unitChecks()
{
  clearStates("index"); setenv("PBR_BASE","4",1);
  for(long i=0;i<4;++i) { aspect::PBR::decide(i,i%2); solve(i%2?30:10,5); }
  require(!aspect::PBR::decide(4,0),"no-aging first reuse");
  auto &s=aspect::PBR::state();
  require(aspect::PBR::phaseOffset(1)==20 && s.levels==std::vector<double>(4,10),"freeze offsets and levels");
  require(s.tot==60 && s.rMed==5,"rebase total and preserve raw rho");
  solve(10,5);
  require(!aspect::PBR::decide(5,1),"no-aging high phase must not rebuild");
  solve(30,5);
  require(!aspect::PBR::decide(6,0),"no-aging continuation");
  require(s.dN.at(1).back()==0 && s.dN.at(2).back()==0,"same residual coordinate");
  require(aspect::PBR::phaseOffset(27)==0,"unseen phase falls back to zero");
  aspect::PBR::markMatrixReset(); aspect::PBR::decide(7,1); solve(5,5);
  aspect::PBR::decide(8,0);
  require(s.levels.back()==-15,"negative modeled count must not be clipped or unsigned");
  require(aspect::PBR::phaseOffset(1)==20,"offsets remain frozen after new rebuild");
  require(s.rSamples.back()==5,"rho uses raw iterations");
  auto count=s.nDone; solve(0,5); aspect::PBR::decide(9,0);
  require(s.nDone==count,"zero raw iterations preserve legacy exclusion");
  aspect::PBR::resetForNewMesh();
  require(!s.offsetsFrozen && s.phaseOffsets.empty() && s.warmSamples.empty(),"mesh reset");
  clearStates("index");setenv("PBR_BASE","2",1);
  aspect::PBR::decide(0,1);solve(10);aspect::PBR::decide(1,1);solve(20);
  aspect::PBR::decide(2,1);
  require(aspect::PBR::phaseOffset(1)==0,"missing reference j=0 disables offsets");
  std::cout<<"unit_checks PASS\n";
}

int main(int argc,char **argv)
{
  try {
    if(argc==2 && std::string(argv[1])=="--unit") {unitChecks();return 0;}
    require(argc==3,"usage: replay events.tsv off|zero");
    const bool zero=std::string(argv[2])=="zero";
    clearStates(zero?"index":"off");
    std::ifstream in(argv[1]);require(bool(in),"input missing");
    long index,j,forced,mesh;unsigned long N;double build,ms;long count=0,rb=0;
    while(in>>index>>j>>N>>build>>ms>>forced>>mesh) {
      if(mesh>=0) {legacy_aspect::PBR::beginSolve(mesh);aspect::PBR::beginSolve(mesh);}
      if(forced) {legacy_aspect::PBR::markMatrixReset();aspect::PBR::markMatrixReset();}
      bool a=legacy_aspect::PBR::decide(index);
      bool b=aspect::PBR::decide(index,zero?0:j);
      require(a==b,"decision mismatch");compare(index);
      require(a==legacy_aspect::PBR::decide(index) && b==aspect::PBR::decide(index,zero?0:j),"repeated decision");
      if(build>0) {legacy_aspect::PBR::noteBuildTime(build);aspect::PBR::noteBuildTime(build);}
      legacy_aspect::PBR::noteSolve(N,ms);aspect::PBR::noteSolve(N,ms);
      legacy_aspect::PBR::noteRatio();aspect::PBR::noteRatio();compare(index);
      count++;rb+=b;
    }
    require(count>0,"empty stream");
    std::cout<<"PASS "<<argv[1]<<" mode="<<argv[2]<<" events="<<count<<" rebuilds="<<rb<<"\n";
    return 0;
  } catch(const std::exception &e) {std::cerr<<e.what()<<"\n";return 1;}
}
