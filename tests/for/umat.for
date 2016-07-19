#ifndef umat
#define umat 0
#endif

#include "usub-util.for"
#include "materialProperties.for"


      SUBROUTINE UMAT(STRESS,STATEV,DDSDDE,SSE,SPD,SCD,
     * RPL,DDSDDT,DRPLDE,DRPLDT,
     * STRAN,DSTRAN,TIME,DTIME,TEMP,DTEMP,PREDEF,DPRED,CMNAME,
     * NDI,NSHR,NTENS,NSTATV,PROPS,NPROPS,COORDS,DROT,PNEWDT,
     * CELENT,DFGRD0,DFGRD1,NOEL,NPT,LAYER,KSPT,JSTEP,KINC)

      ! Load modulues
      use materialProperties

      INCLUDE 'ABA_PARAM.INC'

      CHARACTER*80 CMNAME
      DIMENSION STRESS(NTENS),STATEV(NSTATV), &
       DDSDDE(NTENS,NTENS),DDSDDT(NTENS),DRPLDE(NTENS), &
       STRAN(NTENS),DSTRAN(NTENS),TIME(2),PREDEF(1),DPRED(1), &
       PROPS(NPROPS),COORDS(3),DROT(3,3),DFGRD0(3,3),DFGRD1(3,3), &
       JSTEP(4)

      ! == END standard Abaqus umat interface ==

      ! Machine precision
      integer, parameter :: dp = kind(1.d0)

      ! Local
      character(len=80) mat, elementType             ! Stores type of element if it is recognized
      real(dp) :: stiff(ntens, ntens)                ! Stiffness matrix (often written as 'C')
      real(dp) :: strain(ntens)                      ! Strain vector (strain at the start of the increment + dstran)
      type(mproperties) :: p                         ! Material properties

      ! --------------- END declarations ---------------

      ! Identify element type in material name
      call getElementType(cmname, mat, elementType)

      ! Load material properties, p
      call materialProperties_load(nprops, props, p)

      ! Compute the total strain
      do i=1, ntens
        strain(i) = stran(i) + dstran(i)
      end DO

      ! Load the elastic stiffness matrix
      call materialProperties_elasticStiffness(elementType, p, stiff)

      ! Compute the stress vector
      stress = matmul(stiff, strain)


      ! Compute the jacobian (DDSDDE)
      ddsdde = stiff


      RETURN
      END
