
      module materialProperties
        ! Contains code relevant to importing material properties from props array

        ! Data structure for material properties
        ! FYI naming this type "properties" triggered an error, so its named mproperties
        type :: mproperties
          real(kind=kind(1.d0)) :: E1, E2, E3, nu12, nu13, nu23, G12, G13, G23
          real(kind=kind(1.d0)) :: nu21, nu31, nu32
        end type

        ! Machine precision
        integer, parameter, private :: dp = kind(1.d0)


      Contains
        subroutine materialProperties_load(nprops, props, properties)
          ! Loads the props array into a properties object
          ! Material symmetry is handled within this subroutine

#ifdef umat
          include 'aba_param.inc'
#else
          include 'vaba_param.inc'
#endif

          ! Arguments
          integer, intent(in) :: nprops
          dimension props(nprops)  ! Intent in
          type(mproperties), intent(out) :: properties

          ! Locals
          real(dp) :: E, G, nu

          ! Branch depending on nprops
          ! Isotropic
          if (nprops .EQ. 2) then
            properties%E1 = props(1)
            properties%E2 = props(1)
            properties%E3 = props(1)

            properties%nu12 = props(2)
            properties%nu13 = props(2)
            properties%nu23 = props(2)

            G = props(1)/(2*(1+props(2)))
            properties%G12 = G
            properties%G13 = G
            properties%G23 = G

          ! Transversely isotropic
          else if (nprops .EQ. 5) then
            properties%E1 = props(1)
            properties%E2 = props(2)
            properties%E3 = props(2)

            properties%nu12 = props(3)
            properties%nu13 = properties%E1/(2*properties%G13) - 1.d0
            properties%nu23 = properties%E2/(2*properties%G23) - 1.d0

            properties%G12 = props(4)
            properties%G13 = props(5)
            properties%G23 = props(5)

          ! Orthotropic
          else if (nprops .EQ. 9) then
            properties%E1 = props(1)
            properties%E2 = props(2)
            properties%E3 = props(3)

            properties%nu12 = props(4)
            properties%nu13 = props(5)
            properties%nu23 = props(6)

            properties%G12 = props(7)
            properties%G13 = props(8)
            properties%G23 = props(9)

          else
            Call ABQERR(-3,'BAD INPUT. Expecting that nprops is 2, 5, or 9. Received nprops=%I.',nprops,realv,charv)

          end if


          ! Calculate inverse Poisson's ratios
          properties%nu21 = properties%nu12 * (properties%E2/properties%E1)
          properties%nu31 = properties%nu13 * (properties%E3/properties%E1)
          properties%nu32 = properties%nu23 * (properties%E3/properties%E2)


          return
        end subroutine materialProperties_load

        subroutine materialProperties_elasticStiffness(elementType, properties, stiff)
          ! Computes the stiffness tensor

          ! Arguments
          character(len=80), intent(in) :: elementType           ! Stores type of element if it is recognized
          type(mproperties), intent(in) :: properties            ! Material properties
          real(dp), dimension(:,:) :: stiff                                   ! Stiffness matrix

          ! Locals
          real :: preFactor

          ! Define the stiffness matrix
          if ((elementType .EQ. 'CPS') .OR. (elementType .EQ. 'S') .OR. (elementType .EQ. 'SC')) then      ! Plane stress
            stiff = 0.d0
            stiff(1,1) = properties%E1/(1.d0-properties%nu12*properties%nu21)
            stiff(1,2) = (properties%nu12*properties%E2)/(1.d0-properties%nu12*properties%nu21)
            stiff(2,2) = properties%E2/(1.d0-properties%nu12*properties%nu21)
            stiff(2,1) = stiff(1,2)

            ! Handle vumat weirdness where for some reason I don't understand, ndir=3 for plane stress in explicit
            if (size(stiff) .EQ. 9) then
              ! Implicit
              stiff(3,3) = properties%G12
            else
              ! Explicit, where ndir=3
              stiff(4,4) = properties%G12
            end if

          else if ((elementType .EQ. 'CPE') .OR. (elementType .EQ. 'C3D')) then      ! Plane strain and 3D
            preFactor = (1-properties%nu12*properties%nu21-properties%nu23*properties%nu32-properties%nu13*properties%nu31 &
               -2*properties%nu21*properties%nu32*properties%nu13)/(properties%E1*properties%E2*properties%E3)

            stiff = 0.d0
            stiff(1,1) = (1-properties%nu23*properties%nu32)/(properties%E2*properties%E3*preFactor)
            stiff(2,2) = (1-properties%nu13*properties%nu31)/(properties%E1*properties%E3*preFactor)
            stiff(3,3) = (1-properties%nu12*properties%nu21)/(properties%E1*properties%E2*preFactor)
            stiff(1,2) = (properties%nu21+properties%nu31*properties%nu23)/(properties%E2*properties%E3*preFactor)
            stiff(1,3) = (properties%nu31+properties%nu21*properties%nu32)/(properties%E2*properties%E3*preFactor)
            stiff(2,1) = stiff(1,2)
            stiff(2,3) = (properties%nu32+properties%nu12*properties%nu31)/(properties%E1*properties%E3*preFactor)
            stiff(3,1) = stiff(1,3)
            stiff(3,2) = stiff(2,3)
            stiff(4,4) = properties%G12

            ! Additional components for 3D elements
            if (elementType .EQ. 'C3D') then
              stiff(4,4) = properties%G12
#ifdef umat
              stiff(5,5) = properties%G13
              stiff(6,6) = properties%G23
#else
              stiff(5,5) = properties%G23
              stiff(6,6) = properties%G13
#endif
            end if

          else
            Call ABQERR(-3,'Did not find a recognized element type in material name.',intv,realv,charv)

          end if

          return
        end subroutine materialProperties_elasticStiffness

      end module
