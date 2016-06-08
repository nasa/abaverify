#include "usub-util.for"
#include "materialProperties.for"
      
      subroutine vumat(
      ! Read only -
     *  nblock, ndir, nshr, nstatev, nfieldv, nprops, lanneal,
     *  stepTime, totalTime, dt, cmname, coordMp, charLength,
     *  props, density, strainInc, relSpinInc,
     *  tempOld, stretchOld, defgradOld, fieldOld,
     *  stressOld, stateOld, enerInternOld, enerInelasOld,
     *  tempNew, stretchNew, defgradNew, fieldNew,

       ! Write only -
     *  stressNew, stateNew, enerInternNew, enerInelasNew )

      ! Load modulues
      use materialProperties

#ifdef umat
      include 'aba_param.inc'
#else
      include 'vaba_param.inc'
#endif 

      ! All arrays dimensioned by (*) are not used in this algorithm
      dimension props(nprops), density(nblock), coordMp(nblock,*),
     *  charLength(*), strainInc(nblock,ndir+nshr), relSpinInc(*), tempOld(*),
     *  stretchOld(*), defgradOld(*), fieldOld(*), stressOld(nblock,ndir+nshr),
     *  stateOld(nblock,nstatev), enerInternOld(nblock), enerInelasOld(nblock), 
     *  tempNew(*), stretchNew(*), defgradNew(*), fieldNew(*), stressNew(nblock,ndir+nshr), 
     *  stateNew(nblock,nstatev), enerInternNew(nblock), enerInelasNew(nblock)

      character*80 cmname

      ! == END standard Abaqus umat interface ==

      ! Machine precision
      integer, parameter :: dp = kind(1.d0)

      ! Locals
      character(len=80) mat, elementType             ! Stores type of element if it is recognized
      real(dp) :: stiff(ndir+nshr, ndir+nshr)        ! Stiffness tensor (often written as 'C')
      type(mproperties) :: p                         ! Material properties

      ! --------------- END declarations --------------- 

      ! Identify element type in material name
      call getElementType(cmname, mat, elementType)

      ! Load material properties, p
      call materialProperties_load(nprops, props, p)

      ! Load the elastic stiffness matrix
      call materialProperties_elasticStiffness(elementType, p, stiff)

      

      ! nblock loop
      do 100 i = 1, nblock

        ! VUMAT provides tensor shear strain
        ! Convert tensor shear strains to engineering shear strain
        strainInc(i,4:) = 2.d0*strainInc(i,4:)

        ! Compute stress
        stressNew(i,:) = stressOld(i,:) + matmul(stiff, strainInc(i,:))

        ! Change strainInc back to tensor strain
        strainInc(i,4:) = strainInc(i,4:)/2.d0
        
  100 continue


      return
      end