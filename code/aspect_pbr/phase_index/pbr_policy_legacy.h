/*
  PBR: online preconditioner-rebuild policy for ASPECT's Stokes AMG
  (port of the policy in the PBR paper; see code/pbrPETSc/PETScPreconditioner.C).

  Criterion (paper §4): rebuild iff  est = lvl + max(0, delta) > avg,
  with lvl  = iterations observed the last time the preconditioner was rebuilt,
       delta = expected growth of that count at the current age (median at the
               exact age if sampled, otherwise a secant extrapolation of the
               medians at the two largest sampled ages),
       avg  = running mean of the per-step cost (r + iterations since warm-up).

  Environment variables:
    PBR_POLICY = off | fixed | online      (default off = upstream behaviour)
    PBR_K      = k   for "fixed": rebuild every k steps, 0 = never
    PBR_BASE   = b   steps before the end of the warm-up (default 100)
    PBR_LOG    = path  optional per-step CSV trace
*/

#ifndef aspect_pbr_policy_h
#define aspect_pbr_policy_h

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <map>
#include <string>
#include <vector>

namespace aspect
{
  namespace PBR
  {
    inline long envL(const char *name, const long def)
    {
      const char *e = std::getenv(name);
      return e ? std::atol(e) : def;
    }

    inline std::string envS(const char *name, const char *def)
    {
      const char *e = std::getenv(name);
      return std::string(e ? e : def);
    }

    inline double medianOf(std::vector<double> v)
    {
      if (v.empty())
        return 0.0;
      const std::size_t n = v.size() / 2;
      std::nth_element(v.begin(), v.begin() + n, v.end());
      return v[n];
    }

    struct State
    {
      // configuration
      std::string mode = "off";
      bool online = false, fixed = false;
      long K = 1, base = 100;
      bool unitStep = false;   // PBR_UNIT=step: decide once per time step (paper semantics)

      // per-step accumulators
      long          lastStep   = -1;   // step whose solve is being accumulated
      unsigned long stepApplies = 0;   // Krylov iterations done in that step
      double        stepBuildTime = 0.0;
      double        stepSolveTime = 0.0;
      bool          builtThisStep = false;
      long          stepBuilds    = 0;      // number of AMG builds inside the current decision unit
      double        lastBuildMs   = 0.0;    // build time of the build right before the last solve
      bool          lastSolveAfterBuild = false;

      // decision of the step currently being started
      long heldBase = -1, runAge = 0;
      bool rebuild = true, sameStepDecision = false;
      double est = 0.0, avg = 0.0;
      std::string dSrc = "warmup";

      // decision of the step just completed (for the log row)
      long   prevRebuild = 1, prevHeldBase = -1, prevRunAge = 0;
      double prevIts = 0.0, prevEst = 0.0, prevAvg = 0.0;
      double prevBuildTime = 0.0, prevSolveTime = 0.0;
      std::string prevSrc = "warmup";

      // learned quantities
      std::vector<double> levels;                 // iterations in rebuild steps
      std::map<long, std::vector<double> > dN;    // age -> (N - median(levels))
      std::vector<double> rSamples;               // measured r = setup / per-iteration
      double rMed = 0.0, rLast = 0.0;
      double tot = 0.0, acc = 0.0;
      long accn = 0;
      unsigned long nDone = 0;

      // diagnostics
      unsigned long nRebuilds = 0, nSolves = 0;
      unsigned long lastSolveIts = 0;
      double        lastSolveMs  = 0.0;

      // bookkeeping across mesh changes (DoF count) and solve index
      bool initialized = false;
      long long lastMeshM = -1;
      long solveGen = 0;
      bool matrixReset = false;          // set when ASPECT re-creates the matrix object
      unsigned long nForced = 0;

      std::ofstream log;
      bool headerWritten = false;
    };

    inline State &state()
    {
      static State S;
      return S;
    }

    inline void init()
    {
      State &S = state();
      if (S.initialized)
        return;
      S.initialized = true;
      S.mode   = envS("PBR_POLICY", "off");
      S.online = (S.mode == "online");
      S.fixed  = (S.mode == "fixed");
      S.K      = envL("PBR_K", 1);
      S.base   = envL("PBR_BASE", 100);
      S.unitStep = (envS("PBR_UNIT", "solve") == "step");
      const std::string path = envS("PBR_LOG", "");
      if (!path.empty())
        S.log.open(path.c_str());
    }

    /** Forget everything that was learned on the previous mesh. */
    inline void resetForNewMesh()
    {
      State &S = state();
      S.levels.clear();
      S.dN.clear();
      S.rSamples.clear();
      S.tot = S.acc = 0.0;
      S.accn = 0;
      S.nDone = 0;
      S.heldBase = -1;
      S.runAge = 0;
      S.lastStep = -1;
      S.stepApplies = 0;
      S.stepBuildTime = S.stepSolveTime = 0.0;
      S.builtThisStep = false;
      S.sameStepDecision = false;
    }

    inline void writeLogRow(const long step)
    {
      State &S = state();
      if (!S.log.is_open())
        return;
      if (!S.headerWritten)
        {
          S.log << "step,rebuild,heldBase,age,its,est,avg,rMed,est_dsrc,"
                << "build_ms,solve_ms,nRebuilds,tot,acc,accn,nDone\n";
          S.headerWritten = true;
        }
      S.log << step << ',' << S.prevRebuild << ',' << S.prevHeldBase << ',' << S.prevRunAge
            << ',' << S.prevIts << ',' << S.prevEst << ',' << S.prevAvg << ',' << S.rMed
            << ',' << S.prevSrc << ',' << S.prevBuildTime << ',' << S.prevSolveTime
            << ',' << S.nRebuilds << ',' << S.tot << ',' << S.acc << ',' << S.accn
            << ',' << S.nDone << '\n';
      S.log.flush();
    }

    /**
     * Decide whether the Stokes preconditioner must be rebuilt before the solve
     * of @p step. Repeated calls inside the same step return the same answer.
     */
    inline bool decide(const long step)
    {
      init();
      State &S = state();
      if (S.mode == "off")
        return true;

      if (S.lastStep == step && S.sameStepDecision && !S.matrixReset)
        return S.rebuild;

      // ---- 1) fold the solve(s) of the step just completed ----------------
      if (S.lastStep >= 0 && S.stepApplies > 0)
        {
          const double N = static_cast<double>(S.stepApplies);

          S.prevIts         = N;
          S.prevRebuild     = S.rebuild ? 1 : 0;
          S.prevHeldBase    = S.heldBase;
          S.prevRunAge      = S.runAge;
          S.prevEst         = S.est;
          S.prevAvg         = S.avg;
          S.prevSrc         = S.dSrc;
          S.prevBuildTime   = S.stepBuildTime;
          S.prevSolveTime   = S.stepSolveTime;
          writeLogRow(S.lastStep);

          if (S.runAge == 0)
            {
              S.rMed = medianOf(S.rSamples);
              const double c = S.rMed * static_cast<double>(std::max<long>(1, S.stepBuilds)) + N;
              S.tot += c;
              S.levels.push_back(N);
              if (S.lastStep < S.base)
                {
                  S.acc  = 0.0;
                  S.accn = 0;
                }
              else
                {
                  S.acc  = c;
                  S.accn = 1;
                }
            }
          else
            {
              S.tot += N;
              if (!S.levels.empty())
                S.dN[S.runAge].push_back(N - medianOf(S.levels));
              S.acc  += N;
              S.accn += 1;
            }
          ++S.nDone;
        }
      S.stepApplies   = 0;
      S.stepBuildTime = 0.0;
      S.stepSolveTime = 0.0;
      S.builtThisStep = false;
      S.stepBuilds    = 0;
      S.lastStep      = step;

      // ---- 2) decide for this step ----------------------------------------
      bool rebuild = true;
      S.est = 0.0;
      S.avg = 0.0;
      std::string src = "warmup";

      if (S.fixed)
        {
          if (S.heldBase < 0 || S.K == 1)
            rebuild = true;
          else if (S.K == 0)
            rebuild = false;
          else
            rebuild = (step - S.heldBase >= S.K);
          src = "fixed";
        }
      else if (S.online && step >= S.base && S.heldBase >= 0 && !S.levels.empty())
        {
          const long   a   = step - S.heldBase;
          const double lvl = S.levels.back();
          const double avg = (S.accn > 0)
                             ? S.acc / static_cast<double>(S.accn)
                             : S.tot / static_cast<double>(std::max<long>(1, S.nDone));

          double delta = 0.0;
          std::map<long, std::vector<double> >::const_iterator hit = S.dN.find(a);
          if (hit != S.dN.end() && !hit->second.empty())
            {
              delta = medianOf(hit->second);
              src   = "hit";
            }
          else
            {
              std::vector<long> ks;
              for (std::map<long, std::vector<double> >::const_iterator q = S.dN.begin();
                   q != S.dN.end(); ++q)
                if (!q->second.empty())
                  ks.push_back(q->first);

              if (ks.size() >= 2)
                {
                  const long   a2 = ks[ks.size()-1], a1 = ks[ks.size()-2];
                  const double d2 = medianOf(S.dN[a2]), d1 = medianOf(S.dN[a1]);
                  const double sl = (d2 - d1) / std::max(1e-9, static_cast<double>(a2 - a1));
                  delta = d2 + sl * static_cast<double>(a - a2);
                  src   = "extrap";
                }
              else if (ks.size() == 1)
                {
                  delta = medianOf(S.dN[ks[0]]);
                  src   = "flat";
                }
              else
                {
                  src = "boot_none";
                }
            }

          S.est   = lvl + std::max(0.0, delta);
          S.avg   = avg;
          rebuild = (S.est > S.avg);
        }

      if (S.matrixReset && !rebuild)
        {
          rebuild = true;           // the old preconditioner refers to a matrix that no longer exists
          src = "forced_reset";
          ++S.nForced;
        }
      S.matrixReset = false;

      if (rebuild)
        {
          S.heldBase = step;
          S.runAge   = 0;
          ++S.nRebuilds;
        }
      else
        {
          S.runAge = step - S.heldBase;
        }

      S.rebuild          = rebuild;
      S.dSrc             = src;
      S.sameStepDecision = true;
      return rebuild;
    }

    /**
     * Start a new Stokes solve: bump the solve counter and restart the learned
     * state if the mesh (DoF count of the velocity block) changed.
     */
    inline void beginSolve(const long long mesh_m)
    {
      init();
      State &S = state();
      if (S.mode == "off")
        return;
      if (mesh_m != S.lastMeshM)
        {
          S.lastMeshM = mesh_m;
          resetForNewMesh();
        }
      ++S.solveGen;
    }

    /** ASPECT has re-created the system matrix (sparsity pattern): the next solve must rebuild. */
    inline void markMatrixReset()
    {
      init();
      state().matrixReset = true;
    }

    /** Record how long the rebuild that just happened took (in ms). */
    inline void noteBuildTime(const double ms)
    {
      init();
      State &S = state();
      S.stepBuildTime += ms;
      S.builtThisStep = true;
      ++S.stepBuilds;
      S.lastBuildMs = ms;
      S.lastSolveAfterBuild = true;
    }

    /** Record the Krylov iterations and wall time of one Stokes solve (ms). */
    inline void noteSolve(const unsigned long its, const double ms)
    {
      init();
      State &S = state();
      if (!S.online && !S.fixed)
        return;
      S.stepApplies   += its;
      S.stepSolveTime += ms;
      ++S.nSolves;
      S.lastSolveIts = its;
      S.lastSolveMs  = ms;
    }

    /** After a solve that followed a rebuild: learn r = setup / per-iteration. */
    inline void noteRatio()
    {
      init();
      State &S = state();
      if ((!S.online && !S.fixed) || !S.lastSolveAfterBuild)
        return;
      S.lastSolveAfterBuild = false;
      if (S.lastBuildMs <= 0.0 || S.lastSolveIts == 0 || S.lastSolveMs <= 0.0)
        return;
      const double perIt = S.lastSolveMs / static_cast<double>(S.lastSolveIts);
      const double r = S.lastBuildMs / perIt;
      if (r > 0.0 && r < 1e7)
        {
          S.rLast = r;
          S.rSamples.push_back(r);
        }
    }
  }
}

#endif
