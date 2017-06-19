      
      subroutine ABQERR(lop, string, intv, realv, charv)
        ! Generic call to report error in subroutine
        ! Abstracts the differences between implicit and explicit subroutines

        ! Arguments (all are intent in)
        integer :: lop
        character*500 string
        character*8 charv(*)
        dimension intv(*),realv(*)



#ifdef umat
        Call STDB_ABQERR(lop, string, intv, realv, charv)
#else
        Call XPLB_ABQERR(lop, string, intv, realv, charv)
#endif

        return
      end


      subroutine splitAtFirstMatch(string, char, firstHalf, secondHalf)
        ! Attempts to split a string at the specified char
        ! Returns an array of the two parts of the string in output
        ! If no match is found, the second value of the array output is empty
        ! Uses a brute force search
        ! String length is limited to 500 

        ! Arguments
        character(len=*), intent (in) :: string
        character(len=1), intent (in) :: char
        character(len=*), intent (out) :: firstHalf, secondHalf


        ! Brute force search
        i = scan(string, char)
        if (i .GT. 0) then
          firstHalf = string(:i-1)
          secondHalf = string(i+1:)
        else
          firstHalf = string
          secondHalf = ''
        end if

        return
      end

      subroutine getElementType(cmname, mat, elementType)
        ! Assumes that the material is named with the convention MATERIALNAME-ELEMENTTYPE
        ! splits on the '-' and returns the material name and elementType

        ! Arguments
        character(len=*), intent(in) :: cmname
        character(len=*), intent(out) :: mat, elementType

        ! Locals
        character(len=80) :: empty

        call splitAtFirstMatch(cmname, '-', mat, elementType)
        if (elementType .EQ. empty) then
          Call ABQERR(-3,'Found element type null in material name.',intv,realv,charv)
        
        else if (index(elementType,'CPS') .GT. 0) then
          elementType = 'CPS'
        
        else if (index(elementType,'CPE') .GT. 0) then
          elementType = 'CPE'

        else if (index(elementType, 'C3D') .GT. 0) then
          elementType = 'C3D'

        else if (index(elementType, 'SC') .GT. 0) then
          elementType = 'SC'

        else if (index(elementType, 'S') .GT. 0) then
          elementType = 'S'

        else
          Call ABQERR(-3,'Did not find a recognized element type in material name.',intv,realv,charv)

        end if

        return
      end